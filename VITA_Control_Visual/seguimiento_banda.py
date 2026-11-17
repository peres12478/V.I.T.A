"""Seguimiento de fechas en banda y votacion temporal de calidad fisica.

- Cada ID pertenece a una region fisica seguida, no a un lote de N fotos.
- Una vez decidido, el ID y la decision quedan bloqueados hasta confirmar salida.
- Cada N fotos significa N CAPTURAS TOTALES; tambien cuentan las no evaluables.
- Para PASA se requieren al menos cinco BUENAS y predominio sobre MALAS. Objetivo es MAXIMO, no minimo de capturas.
- REVISAR/borrosa ocupa una captura, pero NO suma votos a ningun lado.
- El modo bloqueo_unico esta pensado para UNA posicion de inspeccion/lane.
- No identifica empaques pegados: requieren separacion o sensor de presencia.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import math

from validacion_visibilidad import VerificadorVisibilidad

Caja = Tuple[int, int, int, int]


@dataclass(frozen=True)
class Observacion:
    caja: Caja
    estado: str                         # BIEN / MAL / REVISAR
    motivo: str = ""
    nitidez: Optional[float] = None


@dataclass(frozen=True)
class EventoFinal:
    id: int
    estado: str                         # BIEN / MAL (decision binaria)
    motivo: str
    buenas: int
    malas: int
    ambiguas: int
    desenfocadas: int
    total: int                          # Capturas TOTALES tomadas (buenas + malas + dudosas)
    instante: float
    cuadro: int
    cierre: str                         # objetivo, desaparecio, reinicio
    dudosas_ignoradas: int = 0

    @property
    def validas(self) -> int:
        return self.buenas + self.malas


@dataclass
class Pista:
    id: int
    caja: Caja
    ultimo_tiempo: float
    ultimo_cuadro: int
    centro_anterior: Optional[Tuple[float, float]] = None
    velocidad: Tuple[float, float] = (0., 0.)
    primer_tiempo: float = 0.
    ultimo_muestreo: Optional[float] = None
    buenas: int = 0
    malas: int = 0
    ambiguas: int = 0
    desenfocadas: int = 0
    dudosas_ignoradas: int = 0  # reservado por compatibilidad
    muestreos: int = 0
    faltas: int = 0
    estado_final: Optional[str] = None
    motivo_final: str = ""
    ultimo_motivo: str = ""
    ultima_muestra: str = "SIN FOTO"
    caja_visual: Optional[Tuple[float, float, float, float]] = None
    visibilidad: VerificadorVisibilidad = field(default_factory=VerificadorVisibilidad)

    @property
    def validas(self) -> int:
        return self.buenas + self.malas

    @property
    def centro(self) -> Tuple[float, float]:
        return _centro(self.caja)

    @property
    def caja_mostrada(self) -> Caja:
        if self.caja_visual is None:
            return self.caja
        return tuple(int(round(v)) for v in self.caja_visual)

    def actualizar_posicion(self, caja: Caja, t: float, cuadro: int) -> None:
        viejo = self.centro
        nuevo = _centro(caja)
        dt = max(.00001, t - self.ultimo_tiempo)
        vx = (nuevo[0] - viejo[0]) / dt
        vy = (nuevo[1] - viejo[1]) / dt
        self.velocidad = (
            self.velocidad[0] * .45 + vx * .55,
            self.velocidad[1] * .45 + vy * .55,
        )
        anterior = self.caja_visual or tuple(float(v) for v in self.caja)
        # Suavizado SOLO para la imagen; los calculos usan la deteccion real.
        alpha = .55 if _iou(self.caja, caja) >= .15 else .80
        self.caja_visual = tuple((1-alpha)*v + alpha*n for v,n in zip(anterior, caja))
        self.centro_anterior = viejo
        self.caja = caja
        self.ultimo_tiempo = t
        self.ultimo_cuadro = cuadro
        self.faltas = 0

    def registrar(self, ob: Observacion, t: float, intervalo: float, min_nitidez: float,
                  intervalo_dudosa: float = .45, max_dudosas: int = 3) -> bool:
        """UNA foto = UN intento, sea BIEN, MAL o REVISAR.

        El intervalo se aplica por igual a todos los estados para impedir
        rafagas de inciertas. Los argumentos de antiguas limitaciones de
        incertidumbre se conservan solo por compatibilidad con otros scripts.
        """
        if self.estado_final is not None:
            return False
        if self.ultimo_muestreo is not None and t - self.ultimo_muestreo < intervalo - 1e-8:
            return False
        self.ultimo_muestreo = t
        self.muestreos += 1
        self.ultimo_motivo = ob.motivo
        desenfocada = (min_nitidez > 0 and ob.nitidez is not None and
                        ob.nitidez < min_nitidez)
        if desenfocada:
            self.desenfocadas += 1
            self.ultima_muestra = 'REVISAR'
        elif ob.estado == 'BIEN':
            self.buenas += 1
            self.ultima_muestra = 'BIEN'
        elif ob.estado == 'MAL':
            self.malas += 1
            self.ultima_muestra = 'MAL'
        else:
            self.ambiguas += 1
            self.ultima_muestra = 'REVISAR'
        return True


def _centro(caja: Caja) -> Tuple[float, float]:
    x1, y1, x2, y2 = caja
    return ((x1+x2)*.5, (y1+y2)*.5)


def _iou(a: Caja, b: Caja) -> float:
    x1=max(a[0],b[0]);y1=max(a[1],b[1]);x2=min(a[2],b[2]);y2=min(a[3],b[3])
    inter=max(0,x2-x1)*max(0,y2-y1)
    aa=max(1,a[2]-a[0])*max(1,a[3]-a[1])
    ab=max(1,b[2]-b[0])*max(1,b[3]-b[1])
    return inter/max(1.,aa+ab-inter)


def _parecido(p: Pista, caja: Caja, t: float, max_distancia: float) -> float:
    """Relaciona recuadros por posicion, movimiento, solape y escala."""
    a=p.caja
    area_a=max(1,a[2]-a[0])*max(1,a[3]-a[1])
    area_b=max(1,caja[2]-caja[0])*max(1,caja[3]-caja[1])
    razon=min(area_a,area_b)/max(area_a,area_b)
    if razon < .30:
        return -1.
    dt=max(0., t-p.ultimo_tiempo)
    pcx,pcy=p.centro
    pcx+=p.velocidad[0]*dt
    pcy+=p.velocidad[1]*dt
    cx,cy=_centro(caja)
    diagonal_a=math.hypot(a[2]-a[0], a[3]-a[1])
    diagonal_b=math.hypot(caja[2]-caja[0], caja[3]-caja[1])
    escala=max(20., .5*(diagonal_a+diagonal_b))
    distancia=math.hypot(cx-pcx,cy-pcy)/escala
    solape=_iou(a,caja)
    if distancia>max_distancia and solape < .10:
        return -1.
    return 2.0*solape + max(0.,max_distancia-distancia) + .4*razon


def _puede_continuar_bloqueo(p: Pista, caja: Caja) -> bool:
    """Plan B ante salto de YOLO, solo en carril unico y un recuadro.

    No acepta cambios extremos que claramente pertenezcan a otra region.
    """
    a=p.caja
    area_a=max(1,a[2]-a[0])*max(1,a[3]-a[1])
    area_b=max(1,caja[2]-caja[0])*max(1,caja[3]-caja[1])
    if min(area_a,area_b)/max(area_a,area_b) < .22:
        return False
    diagonal=max(20., .5*(math.hypot(a[2]-a[0],a[3]-a[1]) +
                          math.hypot(caja[2]-caja[0],caja[3]-caja[1])))
    return math.dist(_centro(a),_centro(caja)) <= 2.5*diagonal


@dataclass
class EstadoCuadro:
    asignaciones: List[Tuple[int, Pista]] = field(default_factory=list)
    indices: List[int] = field(default_factory=list)  # indice de Observacion/resultado
    muestras: List[Tuple[int, int, str, Caja]] = field(default_factory=list)
    eventos: List[EventoFinal] = field(default_factory=list)


class SeguimientoBanda:
    def __init__(self, objetivo: int = 7, min_validas: int = 3,
                 intervalo_s: float = .075, max_ausencia_s: float = .65,
                 max_sin_ver: int = 3, proporcion_minima: float = .5,
                 max_muestras: Optional[int] = None, min_nitidez: float = 0.,
                 distancia_max: float = 1.8,
                 bloqueo_unico: bool = False,
                 intervalo_dudosa_s: float = .45,
                 max_dudosas: int = 3,
                 min_buenas: int = 5, control_visibilidad: bool = False,
                 margen_seguro: float = .08, confirmaciones: int = 3,
                 tolerancia_tamano: float = .22):
        if max_muestras is None:
            max_muestras = objetivo
        if min_buenas < 1 or not 0 <= margen_seguro < .4 or confirmaciones < 1 or not 0 <= tolerancia_tamano < 1:
            raise ValueError('Parametros de aprobacion/visibilidad invalidos')
        if objetivo < 1 or min_validas < 1 or min_validas > objetivo:
            raise ValueError('Se requiere 1 <= min_validas <= objetivo')
        if not 0. <= proporcion_minima <= 1.:
            raise ValueError('proporcion_minima debe estar entre 0 y 1')
        if (intervalo_s < 0 or max_ausencia_s <= 0 or max_sin_ver < 1 or
                max_muestras < objetivo or intervalo_dudosa_s < 0 or max_dudosas < 0):
            raise ValueError('Configuracion de tiempos/muestras invalida')
        self.objetivo=objetivo
        self.min_buenas=min_buenas
        self.control_visibilidad=control_visibilidad
        self.margen_seguro=margen_seguro
        self.confirmaciones=confirmaciones
        self.tolerancia_tamano=tolerancia_tamano
        self.min_validas=min_validas
        self.intervalo_s=intervalo_s
        self.max_ausencia_s=max_ausencia_s
        self.max_sin_ver=max_sin_ver
        self.proporcion_minima=proporcion_minima
        # Se conserva el parametro por compatibilidad, pero el numero de
        # capturas nunca supera objetivo. Para hacer 15 fotos, usa --fotos 15.
        self.max_muestras=objetivo
        self.min_nitidez=min_nitidez
        self.distancia_max=distancia_max
        self.bloqueo_unico=bloqueo_unico
        self.intervalo_dudosa_s=intervalo_dudosa_s
        self.max_dudosas=max_dudosas
        self.pistas: Dict[int,Pista]={}
        self.proximo_id=1
        self.ultimo_evento: Optional[EventoFinal]=None

    def _terminar(self,p:Pista,t:float,cuadro:int,cierre:str)->EventoFinal:
        """Emitir un resultado con la evidencia reunida al salir el empaque.

        `objetivo` es el maximo de capturas, no un minimo obligatorio. Una
        salida anticipada con 41 BUENAS / 0 MALAS NO se convierte en rechazo
        solo por no llegar a 50. La validez de cada BUENA corresponde al
        inspector y a sus comprobaciones de integridad fisica.
        """
        if p.validas == 0:
            estado = 'MAL'
            motivo = 'SIN VOTOS EVALUABLES: NO PASA preventivo; defecto no confirmado'
        elif p.malas > p.buenas:
            estado = 'MAL'
            motivo = (f'MAYORIA MALA: {p.malas} malas > {p.buenas} buenas '
                      f'({p.validas} votos evaluables de {p.muestreos} capturas)')
        elif p.buenas == p.malas:
            estado = 'MAL'
            motivo = (f'EMPATE {p.buenas} a {p.malas}: NO PASA preventivo; '
                      'defecto no confirmado')
        elif p.buenas < self.min_buenas:
            estado = 'MAL'
            motivo = (f'BUENAS INSUFICIENTES: {p.buenas}/{self.min_buenas} buenas, '
                      f'{p.validas}/{self.min_validas} evaluables; '
                      f'{p.malas} malas y {p.ambiguas + p.desenfocadas} inciertas; '
                      'NO PASA preventivo, defecto no confirmado')
        else:
            estado = 'BIEN'
            motivo = (f'MAYORIA BUENA Y MINIMO CUMPLIDO: {p.buenas} buenas > {p.malas} malas; '
                      f'minimo {self.min_buenas} buenas; '
                      f'({p.validas} votos evaluables de {p.muestreos} capturas; '
                      f'maximo previsto {self.objetivo})')

        advertencias=[]
        if p.validas < self.min_validas:
            advertencias.append(f'solo {p.validas} votos evaluables')
        if p.validas / max(1, p.muestreos) < self.proporcion_minima:
            advertencias.append('muchas capturas inciertas')
        if p.muestreos < self.objetivo:
            advertencias.append(f'el producto salio antes de {self.objetivo} capturas (no invalida votos suficientes)')
        if advertencias:
            motivo += ' | AVISO DE CONFIABILIDAD: ' + ', '.join(advertencias)
        p.estado_final=estado
        p.motivo_final=motivo
        evento=EventoFinal(p.id,estado,motivo,p.buenas,p.malas,p.ambiguas,
                           p.desenfocadas,p.muestreos,t,cuadro,cierre,p.dudosas_ignoradas)
        self.ultimo_evento=evento
        return evento

    def _retirar_antiguas(self,t:float,cuadro:int,eventos:List[EventoFinal])->None:
        """Cerrar SOLO tras un hueco confirmado: tiempo Y fotogramas sin YOLO."""
        for id_,p in list(self.pistas.items()):
            if p.faltas>=self.max_sin_ver and t-p.ultimo_tiempo>=self.max_ausencia_s:
                if p.estado_final is None:
                    eventos.append(self._terminar(p,t,cuadro,'desaparecio'))
                del self.pistas[id_]

    def _nueva_pista(self,caja:Caja,t:float,cuadro:int)->Pista:
        id_=self.proximo_id
        self.proximo_id+=1
        p=Pista(id=id_,caja=caja,ultimo_tiempo=t,ultimo_cuadro=cuadro,
                primer_tiempo=t,caja_visual=tuple(float(v) for v in caja))
        self.pistas[id_]=p
        return p

    def actualizar(self, observaciones: List[Observacion], t: float, cuadro: int,
                   forma_frame=None, evaluar=None) -> EstadoCuadro:
        """Actualizar 1 vez por frame. Mantener ID despues de alcanzar objetivo.

        El emparejamiento se realiza ANTES de expirar pistas por tiempo;
        una lectura lenta por si sola nunca crea otro producto.
        """
        salida=EstadoCuadro()
        # Si hubo una AUSENCIA YA CONFIRMADA en frames anteriores, la siguiente
        # deteccion es un producto nuevo aunque este en la misma posicion.
        self._retirar_antiguas(t,cuadro,salida.eventos)
        asignadas: Dict[int,int]={}
        usadas=set()
        if self.bloqueo_unico:
            # Solo una zona de inspeccion a la vez; ignorar detecciones extra
            # hasta que el producto anterior deje realmente la camara.
            if self.pistas:
                id_,p=next(iter(self.pistas.items()))
                scores=[(_parecido(p,ob.caja,t,self.distancia_max),i)
                        for i,ob in enumerate(observaciones)]
                scores=[(s,i) for s,i in scores if s>=0]
                if scores:
                    _,i=max(scores)
                    asignadas[i]=id_
                    usadas.add(id_)
                elif len(observaciones)==1 and _puede_continuar_bloqueo(p,observaciones[0].caja):
                    asignadas[0]=id_
                    usadas.add(id_)
            elif observaciones:
                # En ausencia de una pista, la region mas grande se examina;
                # duplicados / recuadros secundarios no crean mas productos.
                i=max(range(len(observaciones)),key=lambda n:
                      max(0,observaciones[n].caja[2]-observaciones[n].caja[0]) *
                      max(0,observaciones[n].caja[3]-observaciones[n].caja[1]))
                p=self._nueva_pista(observaciones[i].caja,t,cuadro)
                asignadas[i]=p.id
                usadas.add(p.id)
        else:
            candidatos=[]
            for i,ob in enumerate(observaciones):
                for id_,p in self.pistas.items():
                    score=_parecido(p,ob.caja,t,self.distancia_max)
                    if score>=0:
                        candidatos.append((score,id_,i))
            candidatos.sort(reverse=True)
            for _,id_,i in candidatos:
                if id_ not in usadas and i not in asignadas:
                    asignadas[i]=id_
                    usadas.add(id_)
            for i,ob in enumerate(observaciones):
                if i not in asignadas:
                    p=self._nueva_pista(ob.caja,t,cuadro)
                    asignadas[i]=p.id
                    usadas.add(p.id)
        for id_,p in list(self.pistas.items()):
            if id_ not in usadas:
                p.faltas+=1
                if self.control_visibilidad:
                    p.visibilidad.perder_deteccion()
        for i in sorted(asignadas):
            ob=observaciones[i]
            p=self.pistas[asignadas[i]]
            if p.ultimo_cuadro!=cuadro:
                p.actualizar_posicion(ob.caja,t,cuadro)
            # Se cuenta UNA captura solo si la fecha esta totalmente dentro
            # de la zona central y estable durante varios cuadros consecutivos.
            apta = True
            if self.control_visibilidad:
                if forma_frame is None:
                    raise ValueError('forma_frame es obligatoria con control_visibilidad')
                apta = p.visibilidad.verificar(ob.caja, forma_frame,
                    margen=self.margen_seguro, confirmaciones=self.confirmaciones,
                    tolerancia=self.tolerancia_tamano)
            # Importante: no volver a ejecutar el inspector cuando ya se decidio
            # ni cuando el intervalo entre fotografias no ha transcurrido.
            toca = (p.estado_final is None and apta and
                    (p.ultimo_muestreo is None or
                     t - p.ultimo_muestreo >= self.intervalo_s - 1e-8))
            ob_evaluada = (evaluar(p, ob, i) if toca and evaluar is not None else ob)
            if toca and p.registrar(ob_evaluada, t, self.intervalo_s, self.min_nitidez,
                                    self.intervalo_dudosa_s, self.max_dudosas):
                salida.muestras.append((p.id,p.muestreos,p.ultima_muestra,ob.caja))
            salida.asignaciones.append((p.id,p))
            salida.indices.append(i)
            if p.estado_final is None and p.muestreos>=self.objetivo:
                salida.eventos.append(self._terminar(p,t,cuadro,'objetivo'))
        self._retirar_antiguas(t,cuadro,salida.eventos)
        return salida

    def invalidar_por_falla_camara(self, t: float, cuadro: int) -> List[EventoFinal]:
        """Cerrar productos pendientes como NO PASA por FALTA DE CAPTURA.

        Una camara bloqueada o congelada no es evidencia de tinta defectuosa,
        ni puede habilitar una aprobacion con fotografias antiguas.
        No retracta decisiones que ya fueron emitidas antes de la falla.
        """
        eventos = []
        for p in self.pistas.values():
            if p.estado_final is None:
                motivo = 'INSPECCION INTERRUMPIDA: camara sin imagen util; NO PASA preventivo (defecto no confirmado)'
                p.estado_final = 'MAL'
                p.motivo_final = motivo
                evento = EventoFinal(p.id, 'MAL', motivo, p.buenas, p.malas,
                                    p.ambiguas, p.desenfocadas, p.muestreos,
                                    t, cuadro, 'falla_camara', p.dudosas_ignoradas)
                eventos.append(evento)
                self.ultimo_evento = evento
        self.pistas.clear()
        return eventos

    def cerrar(self,t:float,cuadro:int)->List[EventoFinal]:
        eventos=[]
        for id_,p in list(self.pistas.items()):
            if p.estado_final is None:
                eventos.append(self._terminar(p,t,cuadro,'reinicio'))
            del self.pistas[id_]
        return eventos
