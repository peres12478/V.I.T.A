"""Inspeccion fisica de tinta sin OCR ni reglas sobre fechas.

Salida TRI-ESTADO: BIEN (tamizaje preliminar), MAL (indicio fuerte), REVISAR
(no hay evidencia suficiente). Los umbrales son iniciales, NO validados.

No se cuentan caracteres, ni se analizan cadenas, ni se impone formato.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import cv2
import numpy as np
from deteccion_arrastre_interno import detectar_arrastre_interno

FEATURE_NAMES = (
    "snr_contraste", "contraste_tinta", "fraccion_tinta",
    "fraccion_tinta_suave", "indice_halo", "grosor_medio",
    "indice_grosor", "fraccion_gruesa", "indice_manchas",
    "indice_reparacion", "fraccion_rayas", "indice_barrido", "indice_bulto", "laplaciano_normalizado",
    "area_roi", "tamano_menor_roi"
)


@dataclass
class Resultado:
    estado: str
    motivo: str
    puntaje: float
    metricas: Dict[str, float]
    defectos: List[str] = field(default_factory=list)
    mascara_tinta: Optional[np.ndarray] = None
    mascara_sospechosa: Optional[np.ndarray] = None
    polaridad: str = "desconocida"

    def caracteristicas(self) -> np.ndarray:
        return np.array([self.metricas.get(k, 0.) for k in FEATURE_NAMES], dtype=np.float32)


def _odd(v: float, minimo: int = 3, maximo: int = 71) -> int:
    n = max(minimo, min(maximo, int(round(v))))
    return n if n % 2 else n + 1


def _componentes(mascara: np.ndarray):
    n, lab, stats, cents = cv2.connectedComponentsWithStats(mascara, connectivity=8)
    return n, lab, stats


def _descartar_bordes_ajenos(tinta: np.ndarray) -> tuple[np.ndarray, int]:
    """Excluye solamente bandas LARGAS pegadas al marco del recorte YOLO.

    Un borde de etiqueta o barra de empaque suele tocar el marco y recorrer
    gran parte de un eje. No se exige ningun formato o cantidad de caracteres.
    Nunca se borran elementos pequenos como puntos, dos puntos o guiones.
    Si no hay tinta restante, conservamos la entrada: falta evidencia.
    """
    h, w = tinta.shape
    n, labels, stats = _componentes(tinta)
    if n <= 1:
        return tinta, 0
    fuera = np.zeros_like(tinta)
    ignoradas = 0
    borde = max(2, min(5, round(min(h, w) * .055)))
    for i in range(1, n):
        x, y, ancho, alto, area = (int(v) for v in stats[i])
        # Una franja ancha/larga que queda fuera de la zona central del
        # sello puede ser borde de etiqueta, incluso sin tocar el marco.
        horizontal = ancho >= .66 * w and alto <= max(9, .19 * h)
        vertical = alto >= .66 * h and ancho <= max(9, .19 * w)
        al_lado = ((horizontal and (y + alto/2 < .30*h or y + alto/2 > .70*h))
                   or (vertical and (x + ancho/2 < .30*w or x + ancho/2 > .70*w)))
        toca = (x <= borde or y <= borde or
                x + ancho >= w - borde or y + alto >= h - borde)
        if (toca or al_lado) and (horizontal or vertical) and area >= 12:
            fuera[labels == i] = 1
            ignoradas += 1
    filtrada = tinta & (1 - fuera)
    if np.count_nonzero(filtrada) < max(12, .002 * h * w):
        return tinta, 0
    return filtrada, ignoradas


def _score_polaridad(contrast: np.ndarray, noise: float, h: int, w: int) -> float:
    """Prefiere trazos compactos, no un reflejo enorme o una sombra."""
    cutoff = max(3.0, 2.8 * noise, 0.25 * float(np.percentile(contrast, 99)))
    mask = (contrast > cutoff).astype(np.uint8)
    n, _, stats = _componentes(mask)
    if n <= 1:
        return 0.0
    pixels = h * w
    # Solo para seleccionar tinta clara/oscura; NO clasifica por numero de caracteres.
    valid_area = 0.
    for s in stats[1:]:
        x,y,cw,ch,area = map(int, s)
        if 2 <= area <= max(20, pixels * 0.20) and cw < w * 0.96 and ch < h * 0.96:
            valid_area += min(area, pixels * 0.035)
    return (valid_area / max(pixels, 1)) * float(np.percentile(contrast, 98))


class InspectorCalidad:
    def __init__(self, polaridad: str = "automatica", modelo_calidad: Optional[str] = None):
        if polaridad not in ("automatica", "oscura", "clara", "color"):
            raise ValueError("polaridad: automatica, oscura, clara o color")
        self.polaridad = polaridad
        self.clasificador = None
        if modelo_calidad:
            try:
                import joblib
            except ImportError as exc:
                raise RuntimeError("Para cargar un clasificador instala scikit-learn y joblib") from exc
            # Cargar solamente modelos propios de una fuente CONFIABLE (joblib/pickle).
            obj = joblib.load(modelo_calidad)
            if obj.get("feature_names") != FEATURE_NAMES:
                raise ValueError("El modelo de calidad no coincide con el extractor actual")
            self.clasificador = obj["clasificador"]

    def analizar(self, recorte_bgr: np.ndarray) -> Resultado:
        if recorte_bgr is None or recorte_bgr.size == 0:
            return Resultado("REVISAR", "Recorte vacio", 0., {})
        if recorte_bgr.ndim == 2:
            recorte_bgr = cv2.cvtColor(recorte_bgr, cv2.COLOR_GRAY2BGR)
        h, w = recorte_bgr.shape[:2]
        if min(h, w) < 22 or h * w < 1000:
            return Resultado("REVISAR", "Fecha demasiado pequena para inspeccion de trazos", 0., {
                "tamano_menor_roi": float(min(h,w))})

        # LAB desacopla luminancia y crominancia; correccion suave de iluminacion.
        lab = cv2.cvtColor(recorte_bgr, cv2.COLOR_BGR2LAB)
        lum = lab[:,:,0].astype(np.float32)
        sigma = max(3., min(15., min(h,w)/10.))
        fondo = cv2.GaussianBlur(lum, (0,0), sigmaX=sigma)
        residual = lum - fondo
        # Estimacion robusta del ruido de la superficie, no de caracteres.
        noise = max(1.0, float(np.median(np.abs(residual - np.median(residual)))) * 1.4826)
        oscura = np.maximum(-residual, 0.)
        clara = np.maximum(residual, 0.)
        # Alternativa cromatica cuando la tinta cambia el color pero apenas
        # modifica la luminancia (sobre envases de colores diversos).
        ab = lab[:,:,1:].astype(np.float32)
        ab_bg = cv2.GaussianBlur(ab, (0,0), sigmaX=sigma)
        ab_resid = ab-ab_bg
        cromatica_abs = np.sqrt(np.sum(np.square(ab_resid),axis=2))
        # Un gradiente cromatico crea halos en AMBOS sentidos del trazo.
        # Aprender una direccion cromatica dominante elimina el halo opuesto.
        strongest = cromatica_abs >= float(np.percentile(cromatica_abs,99.2))
        dominante = np.median(ab_resid[strongest],axis=0)
        magnitud = float(np.linalg.norm(dominante))
        if magnitud > .5:
            direccion = dominante / magnitud
            cromatica = np.maximum(np.einsum('hwc,c->hw',ab_resid,direccion),0.)
        else:
            cromatica = cromatica_abs
        noise_color = max(1.,float(np.median(np.abs(cromatica-np.median(cromatica))))*1.4826)
        p = self.polaridad
        if p == "automatica":
            sd = _score_polaridad(oscura, noise, h, w)
            sl = _score_polaridad(clara, noise, h, w)
            sc = _score_polaridad(cromatica, noise_color, h, w)
            # Las transiciones de un trazo oscuro producen un halo CLARO
            # por el filtro local. Elegir solo por area produce falsos
            # defectos: priorizar el pico de contraste real de la tinta.
            pico_d = float(np.percentile(oscura,99.5))
            pico_l = float(np.percentile(clara,99.5))
            if pico_d > pico_l*1.30:
                p = "oscura"
            elif pico_l > pico_d*1.30:
                p = "clara"
            else:
                p = "oscura" if sd >= sl else "clara"
            if (sc > max(sd,sl)*1.6 and
                np.percentile(cromatica,99.5)>max(pico_d,pico_l)*1.3 and
                np.percentile(cromatica,99.5)>8):
                p = "color"
        if p == "color":
            contraste = cromatica
            noise = noise_color
        else:
            contraste = oscura if p == "oscura" else clara
        p99 = float(np.percentile(contraste, 99))
        u8 = np.uint8(np.clip(contraste * (255/max(p99*1.6, 10)), 0, 255))
        umbral_otsu, _ = cv2.threshold(u8, 0, 255, cv2.THRESH_BINARY+cv2.THRESH_OTSU)
        umbral_otsu = (float(umbral_otsu)/255.) * max(p99 * 1.6, 10)
        umbral = max(2.8, noise*2.7, p99 * .22, umbral_otsu * .6)
        tinta = np.uint8(contraste >= umbral)
        # Eliminar SOLO bandas de empaque extensas que toquen el marco de YOLO.
        # Esto no trata de reconocer caracteres ni modifica el texto impreso.
        tinta, bandas_ajenas = _descartar_bordes_ajenos(tinta)
        # No se elimina automaticamente la puntuacion ni los trazos pequenos.
        npix = float(h * w)
        tinta_ratio = float(np.mean(tinta))
        tenue = np.uint8(contraste > max(1.8, noise * 1.25, umbral * .38))
        tenue_ratio = float(np.mean(tenue))
        sig = contraste[tinta > 0]
        local_contraste = float(np.median(sig)) if sig.size else 0.
        snr = local_contraste / noise
        
        # Magnitudes de tinta fuera del nucleo: candidatas a arrastre, NO prueba.
        grosor_est = 1.
        variacion_grosor = 1.
        fraccion_gruesa = 0.
        indice_bulto = 1.
        if np.any(tinta):
            distancia = cv2.distanceTransform(tinta, cv2.DIST_L2, 3)
            maximos = distancia >= cv2.dilate(distancia, np.ones((3,3),np.uint8)) - 0.03
            diametros = 2 * distancia[(tinta>0)&maximos]
            if len(diametros):
                grosor_est = max(1., float(np.median(diametros)))
                variacion_grosor = float(np.percentile(diametros,90)/grosor_est)
                indice_bulto = float(np.max(diametros)/grosor_est)
                fraccion_gruesa = float(np.mean(distancia[tinta>0] > 1.85 * grosor_est/2.))

        n, etiquetas, stats = _componentes(tinta)
        # Indice de masas anormalmente grandes en relacion con trazos locales.
        areas = [float(s[cv2.CC_STAT_AREA]) for s in stats[1:] if s[cv2.CC_STAT_AREA] >= 3]
        if len(areas) >= 4:
            ref_area = max(float(np.percentile(areas,50)), 3.)
            manchas = float(max(areas)/ref_area)
        else:
            manchas = 1.

        # Cierre MINIMO: pequenos huecos / desconexiones; nunca se reescribe fecha.
        k = max(2, min(4, int(round(grosor_est * 1.15))))
        cierre = cv2.morphologyEx(tinta, cv2.MORPH_CLOSE, np.ones((k,k),np.uint8))
        reparacion = float(np.count_nonzero((cierre>0)&(tinta==0)) / max(np.count_nonzero(tinta),1))

        # Enfoque local: el fondo del empaque no es un defecto de impresion.
        # El radio depende del grosor medido, NO del tamano de la caja YOLO.
        # Esto sustituye la vecindad amplia previa (hasta 61 x 61 px).
        radio = int(np.clip(round(grosor_est * 1.75), 2, 7))
        k_cerca = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE, (radio * 2 + 1, radio * 2 + 1))
        vecindad = cv2.dilate(tinta, k_cerca)
        halo = np.uint8((tenue > 0) & (tinta == 0) & (vecindad > 0))
        indice_halo = float(np.count_nonzero(halo) / max(np.count_nonzero(tinta), 1))

        # El barrido debe coincidir con trazos REALES y no solo con una linea
        # cualquiera del plastico o de la etiqueta. Se utilizan seis angulos
        # (en vez de doce) para disminuir el tiempo de CPU en una banda.
        # Un trazo exterior alejado no se marca por proximidad accidental.
        baja = np.uint8(contraste > max(1.7, noise * 1.0))
        largo = _odd(max(11, min(27, round(grosor_est * 5.5))))
        lineas = np.zeros_like(tinta)
        for ang in (0, 30, 60, 90, 120, 150):
            kline = np.zeros((largo, largo), dtype=np.uint8)
            centro = largo // 2
            dx = int(round(np.cos(np.deg2rad(ang)) * centro))
            dy = int(round(np.sin(np.deg2rad(ang)) * centro))
            cv2.line(kline, (centro - dx, centro - dy),
                     (centro + dx, centro + dy), 1, 1)
            lineas |= cv2.morphologyEx(baja, cv2.MORPH_OPEN, kline)
        # Rechazar el nucleo impreso (forma de las letras) y conservar
        # unicamente rayas adicionales en la vecindad INMEDIATA.
        corona = cv2.dilate(tinta, np.ones((3, 3), np.uint8))
        barrido = np.uint8((lineas > 0) & (corona == 0) & (vecindad > 0))
        indice_barrido = float(np.count_nonzero(barrido) /
                               max(np.count_nonzero(tinta), 1))
        # Un segundo indice verifica cuantas rayas exteriores estan asociadas
        # a la tinta. Es una pista, no evidencia autonoma de un defecto.
        indice_barrido_bruto = float(np.count_nonzero(lineas & (1 - corona)) /
                                     max(np.count_nonzero(tinta), 1))

        # Rayas axiales blandas solo se admiten cerca de la fecha.
        minimo_raya = max(9, min(25, int(round(grosor_est * 6))))
        raya = np.zeros_like(tinta)
        for forma in ((minimo_raya, 1), (1, minimo_raya)):
            eje = cv2.getStructuringElement(cv2.MORPH_RECT, forma)
            raya |= cv2.morphologyEx(tenue, cv2.MORPH_OPEN, eje)
        raya &= vecindad
        fraccion_rayas = float(np.count_nonzero(raya) /
                               max(np.count_nonzero(tenue & vecindad), 1))

        # Los pixeles resaltados en 06 representan solo indicios localizados.
        # El problema de camara/contraste no se pinta como tinta corrida.
        sospecha = np.zeros_like(tinta)
        if indice_halo > 1.25 and indice_barrido > .12:
            sospecha |= halo
        if variacion_grosor > 2.8 and fraccion_gruesa > .035:
            dist = cv2.distanceTransform(tinta, cv2.DIST_L2, 3)
            sospecha |= np.uint8(dist > 1.85 * grosor_est / 2.)
        if fraccion_rayas > 0.12 and indice_barrido > .10:
            sospecha |= raya & (1 - tinta)
        if indice_barrido > .12:
            sospecha |= barrido
        sospecha &= vecindad
        pixeles_sospechosos = int(np.count_nonzero(sospecha))

        # Metrica de nitidez, solo informativa; baja nitidez no es por si
        # misma un defecto fisico de la impresion.
        lap = cv2.Laplacian(lum,cv2.CV_32F)
        nitidez = float(np.std(lap)/(max(local_contraste,1.)))
        metricas = {
            "snr_contraste": float(snr),
            "contraste_tinta": local_contraste,
            "fraccion_tinta": tinta_ratio,
            "fraccion_tinta_suave": tenue_ratio,
            "indice_halo": indice_halo,
            "grosor_medio": grosor_est,
            "indice_grosor": variacion_grosor,
            "fraccion_gruesa": fraccion_gruesa,
            "indice_manchas": manchas,
            "indice_reparacion": reparacion,
            "fraccion_rayas": fraccion_rayas,
            "indice_barrido": indice_barrido,
            "indice_barrido_bruto": indice_barrido_bruto,
            "radio_busqueda_tinta_px": float(radio),
            "bandas_externas_ignoradas": float(bandas_ajenas),
            "pixeles_sospechosos": float(pixeles_sospechosos),
            "indice_bulto": indice_bulto,
            "laplaciano_normalizado": nitidez,
            "area_roi": npix,
            "tamano_menor_roi": float(min(h,w)),
        }
        defectos=[]
        # Criterios conservadores: NO sumar defectos triviales para condenar.
        # Estas son hipotesis de defecto pendientes de validacion real.
        alta_mancha = (indice_bulto > 5.3 and fraccion_gruesa > .08 and manchas > 3.5)
        # Un barrido localizado solo se considera fuerte si OTRO indicador
        # geometrico (raya axial) tambien lo respalda.
        alto_arrastre = ((indice_barrido > .20 and fraccion_rayas > .22 and snr > 3.0)
                         or (indice_halo > 2.8 and fraccion_rayas > .12
                             and indice_barrido > .12))
        if alta_mancha:
            # La etapa 06 debe localizar la causa del rechazo, no quedarse
            # totalmente vacia ante una mancha gruesa.
            areas_ref = [float(st[cv2.CC_STAT_AREA]) for st in stats[1:]
                         if st[cv2.CC_STAT_AREA] >= 3]
            area_ref = max(3., float(np.median(areas_ref))) if areas_ref else 3.
            for num in range(1, n):
                if stats[num, cv2.CC_STAT_AREA] > max(20., 3.5 * area_ref):
                    sospecha[etiquetas == num] = 1
        pixeles_sospechosos = int(np.count_nonzero(sospecha))
        metricas["pixeles_sospechosos"] = float(pixeles_sospechosos)
        ruptura = (reparacion > .48 and snr > 4.5 and tinta_ratio > .018)
        tenue_importante = (snr < 3.0 and tinta_ratio < .10)
        if alta_mancha:
            defectos.append("Acumulacion importante de tinta")
        if alto_arrastre:
            defectos.append("Posible arrastre/corrimiento de tinta")
        if ruptura:
            defectos.append("Posibles trazos interrumpidos")
        if tenue_importante:
            defectos.append("Tinta de contraste insuficiente")

        # Score de tamizaje, no probabilidad calibrada.
        score = 100. - min(30., max(0., indice_barrido-.08)*80.) \
                     - min(22., max(0., indice_bulto-3.0)*8.) \
                     - min(15., max(0., indice_halo-0.8)*8.) \
                     - min(18., max(0., 4.-snr)*8.)
        score = float(np.clip(score,0,100))
        
        if tinta_ratio < .004 or snr < 2.1:
            estado, motivo = "REVISAR", "Tinta no distinguible del material o imagen insuficiente"
        elif alta_mancha and alto_arrastre:
            estado, motivo = "MAL", "Indicios concordantes de mancha y arrastre"
        elif alto_arrastre and indice_barrido > .22 and fraccion_rayas > .22:
            estado, motivo = "MAL", "Marcas lineales extensas compatibles con tinta corrida"
        elif alta_mancha and indice_bulto > 6.8 and fraccion_gruesa > .10:
            estado, motivo = "MAL", "Acumulacion de tinta muy superior al grosor local"
        elif tenue_importante or ruptura or alto_arrastre or alta_mancha:
            estado, motivo = "REVISAR", "; ".join(defectos)
        elif ((indice_barrido > .12 and fraccion_rayas > .12 and pixeles_sospechosos > 5)
              or (indice_halo > 1.8 and indice_barrido > .08 and pixeles_sospechosos > 5)
              or (variacion_grosor > 3.4 and fraccion_gruesa > .035
                  and pixeles_sospechosos > 5)):
            causas = []
            if indice_barrido > .12 and fraccion_rayas > .12:
                causas.append(f"posible barrido junto a tinta ({indice_barrido:.2f})")
            if indice_halo > 1.8 and indice_barrido > .08:
                causas.append(f"halo proximo a los trazos ({indice_halo:.2f})")
            if variacion_grosor > 3.4 and fraccion_gruesa > .035:
                causas.append(f"grosor irregular ({variacion_grosor:.1f})")
            estado, motivo = "REVISAR", "Anomalia local por comprobar: " + "; ".join(causas)
        else:
            estado, motivo = "BIEN", "Sin indicios graves en los trazos analizados"
            # Un SNR moderado bajo SIN evidencia espacial no puede convertir
            # en defecto la sombra de la superficie. La evaluacion real de
            # camara/desenfoque corresponde a InspectorCalidadRobusto.
            if snr < 5.5:
                motivo += f" | Aviso: contraste relativo limitado (SNR {snr:.1f}); verificar captura"
        resultado = Resultado(estado, motivo, score, metricas, defectos, tinta*255, sospecha*255, p)

        # La segmentacion binaria puede perder un arrastre SEMITRANSPARENTE
        # atravesando varias letras. Buscar crestas paralelas en el recorte
        # BGR original, SOLO dentro de la region asociada a tinta impresa.
        # No se usa OCR ni cantidad de caracteres.
        arrastre_interno = detectar_arrastre_interno(recorte_bgr, resultado.mascara_tinta)
        resultado.metricas['indice_arrastre_interno'] = arrastre_interno.indice
        resultado.metricas['longitud_arrastre_interno'] = arrastre_interno.longitud_relativa
        resultado.metricas['superposicion_arrastre_interno'] = arrastre_interno.superposicion_relativa
        resultado.metricas['bandas_arrastre_interno'] = float(arrastre_interno.bandas_paralelas)
        resultado.metricas['fraccion_arrastre_tinta_fuerte'] = arrastre_interno.fraccion_tinta_fuerte
        if arrastre_interno.fuerte or arrastre_interno.posible:
            resultado.mascara_sospechosa = cv2.bitwise_or(
                resultado.mascara_sospechosa, arrastre_interno.mascara)
            resultado.metricas['pixeles_sospechosos'] = float(
                np.count_nonzero(resultado.mascara_sospechosa))
            if arrastre_interno.fuerte:
                resultado.defectos.append('Arrastre lineal sobre los trazos')
                resultado.estado = 'MAL'
                resultado.motivo = ('Arrastre lineal prolongado que atraviesa la tinta '
                                    f'(longitud relativa {arrastre_interno.longitud_relativa:.2f}, '
                                    f'superposicion {arrastre_interno.superposicion_relativa:.2f})')
                resultado.puntaje = min(resultado.puntaje, 22.)
            elif resultado.estado == 'BIEN':
                resultado.estado = 'REVISAR'
                resultado.motivo = ('Posible arrastre interno sin corroboracion suficiente '
                                    f'({arrastre_interno.indice:.2f}); repetir captura')
        if self.clasificador is not None:
            prob = float(self.clasificador.predict_proba([resultado.caracteristicas()])[0,1])
            resultado.metricas["probabilidad_mal_aprendida"] = prob
            # Rechazo por IA solamente con alta confianza y algun indicio fisico.
            # Conflictos quedan como REVISAR, no como aprobacion automatica.
            indicio = alta_mancha or alto_arrastre or ruptura or indice_barrido > .12 or indice_bulto > 4.5
            if prob >= .90 and indicio:
                resultado.estado = "MAL"
                resultado.motivo = "Defecto corroborado por clasificador supervisado"
                resultado.defectos.append(resultado.motivo)
            elif prob >= .65 and resultado.estado == "BIEN":
                resultado.estado = "REVISAR"
                resultado.motivo = "Anomalia probable segun clasificador"
            elif prob <= .15 and resultado.estado == "MAL":
                resultado.estado = "REVISAR"
                resultado.motivo = "Desacuerdo entre reglas fisicas e IA"
        return resultado


def dibujar_resultado(frame:np.ndarray, box:Tuple[int,int,int,int], resultado:Resultado)->np.ndarray:
    x1,y1,x2,y2 = [int(v) for v in box]
    color = {"BIEN":(35,190,65),"MAL":(40,40,235),"REVISAR":(0,180,255)}.get(resultado.estado,(220,220,220))
    cv2.rectangle(frame,(x1,y1),(x2,y2),color,2)
    titulo = f"{resultado.estado} | inspeccion tinta"
    (tw,th),_ = cv2.getTextSize(titulo,cv2.FONT_HERSHEY_SIMPLEX,.65,2)
    etiqueta_y = max(th+10,y1-8)
    cv2.rectangle(frame,(x1,etiqueta_y-th-8),(min(frame.shape[1]-1,x1+tw+10),etiqueta_y+3),color,-1)
    cv2.putText(frame,titulo,(x1+4,etiqueta_y-3),cv2.FONT_HERSHEY_SIMPLEX,.65,(255,255,255),2,cv2.LINE_AA)
    return frame
