"""Autoriza capturas SOLO cuando el recuadro se ve completo y estable.

No reconoce caracteres ni exige formatos de fecha. La comprobacion observa
solamente geometria, margen al borde de imagen y consistencia de la escala.
Puede haber detecciones parciales que superen la prueba: no sustituye a un
sensor de presencia o a deteccion del contorno completo del empaque.
"""
from dataclasses import dataclass
from typing import Optional, Tuple

Caja = Tuple[int, int, int, int]


@dataclass
class VerificadorVisibilidad:
    consecutivas: int = 0
    habilitada: bool = False
    motivo: str = 'Aguardando fecha completamente visible'
    ultima_dimension: Optional[Tuple[float, float]] = None

    def perder_deteccion(self):
        # La decision previa y los votos permanecen; solo se reinicia la
        # comprobacion de visibilidad para una futura captura.
        self.consecutivas = 0
        self.habilitada = False
        self.ultima_dimension = None
        self.motivo = 'YOLO intermitente; esperando que vuelva la fecha'

    def verificar(self, caja: Caja, forma_frame, margen: float = .08,
                  confirmaciones: int = 3, tolerancia: float = .22) -> bool:
        h, w = forma_frame[:2]
        x1, y1, x2, y2 = caja
        ancho = x2 - x1
        alto = y2 - y1
        if w < 2 or h < 2 or ancho <= 0 or alto <= 0:
            self.perder_deteccion()
            self.motivo = 'Recuadro invalido'
            return False
        # La fecha debe quedar COMPLETA dentro del espacio central. Si
        # entra/sale de la banda, simplemente pausamos las capturas.
        dentro = (x1 >= margen*w and x2 <= (1-margen)*w and
                  y1 >= margen*h and y2 <= (1-margen)*h)
        if not dentro:
            self.perder_deteccion()
            self.motivo = 'Fecha entrando/saliendo: fuera de la zona segura'
            return False
        if self.ultima_dimension is not None:
            aw, ah = self.ultima_dimension
            cambio = max(abs(ancho-aw)/max(ancho,aw,1.),
                         abs(alto-ah)/max(alto,ah,1.))
            if cambio > tolerancia:
                self.consecutivas = 1
                self.ultima_dimension = (float(ancho), float(alto))
                self.habilitada = False
                self.motivo = 'Recuadro variando de tamano; esperar estabilidad'
                return False
        self.consecutivas += 1
        self.ultima_dimension = (float(ancho), float(alto))
        self.habilitada = self.consecutivas >= confirmaciones
        self.motivo = ('Fecha en zona segura, lista para inspeccion' if self.habilitada
                       else f'Confirmando fecha completa: {self.consecutivas}/{confirmaciones}')
        return self.habilitada
