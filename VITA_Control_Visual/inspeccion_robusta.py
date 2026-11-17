"""Preprocesamiento resistente a camaras e iluminaciones no caracterizadas.

El BGR original se conserva. La luminancia de Lab es un canal auxiliar,
NO reemplaza la imagen a color. Se limita el procesamiento para no inventar
trazos, y se verifica la consistencia de decisiones en variantes de captura.

Las reglas de calidad son provisionales; se deben validar con imagenes
etiquetadas de la camara real antes de automatizar un rechazo fisico.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np

from calidad_impresion import InspectorCalidad, Resultado
from integridad_trazos import detectar_debilitamiento
from barrido_continuidad import detectar_barrido_continuidad
from auditoria_mascara import auditar_mascara_tinta


@dataclass(frozen=True)
class DiagnosticoCaptura:
    contraste_luminancia: float
    contraste_cromatico: float
    ruido_luminancia: float
    ruido_relativo: float
    detalle_relativo: float
    bordes_relativos: float
    saturacion_fraccion: float
    problemas: tuple[str, ...]


def diagnosticar_captura(recorte_bgr: np.ndarray) -> DiagnosticoCaptura:
    """Cuantifica informacion de la captura, NO calidad de impresion.

    Contraste cromatico preserva tinta que puede diferenciarse solo en color.
    Nitidez se mide junto a contraste y gradiente (no laplaciano aislado).
    NO se interpreta una foto poco nitida como tinta fisicamente defectuosa.
    """
    if recorte_bgr.ndim == 2:
        recorte_bgr = cv2.cvtColor(recorte_bgr, cv2.COLOR_GRAY2BGR)
    lab = cv2.cvtColor(recorte_bgr, cv2.COLOR_BGR2LAB)
    lum = lab[:, :, 0]
    l = lum.astype(np.float32)
    rango = float(np.percentile(l, 98) - np.percentile(l, 2))
    # Separar variacion cromatica local del color de fondo.
    ab = lab[:, :, 1:].astype(np.float32)
    sigma = max(3., min(15., min(lum.shape) / 10.))
    bg_ab = cv2.GaussianBlur(ab, (0, 0), sigmaX=sigma)
    chroma = np.sqrt(np.sum((ab - bg_ab)**2, axis=2))
    cromatico = float(np.percentile(chroma, 99))

    # MAD de residual de mediana: ruido impulsivo / alta frecuencia.
    # No corresponde a contar puntos de tinta.
    residuo = l - cv2.medianBlur(lum, 3).astype(np.float32)
    ruido = float(1.4826 * np.median(np.abs(residuo - np.median(residuo))))
    ruido_rel = ruido / max(12., rango)
    suavizada = cv2.GaussianBlur(lum, (3, 3), 0.6)
    lap = cv2.Laplacian(suavizada, cv2.CV_32F)
    gx = cv2.Sobel(suavizada, cv2.CV_32F, 1, 0, 3)
    gy = cv2.Sobel(suavizada, cv2.CV_32F, 0, 1, 3)
    grad = cv2.magnitude(gx, gy)
    detalle_rel = float(np.std(lap) / max(1., rango))
    bordes_rel = float(np.percentile(grad, 98) / max(1., rango))
    saturados = float(np.mean((lum <= 3) | (lum >= 252)))

    problemas = []
    # Si la tinta tiene contraste principalmente cromatico, no exigir
    # una diferencia artificial en escala de grises.
    if rango < 9. and cromatico < 9.:
        problemas.append('contraste insuficiente para distinguir tinta y fondo')
    if saturados > .91 and cromatico < 9.:
        problemas.append('captura casi completamente saturada')
    # Indicador prudente, dependiente de la resolucion: si simultaneamente
    # hay poca respuesta de segundo orden y bordes poco localizados, la
    # imagen no permite confiar en detalles finos de la tinta.
    if (rango >= 15. and cromatico < 20. and
            detalle_rel < .027 and bordes_rel < 1.9):
        problemas.append('detalle fino insuficiente; posible desenfoque o movimiento')
    if ruido > 6. and ruido_rel > .155:
        problemas.append('ruido de captura elevado respecto al contraste')
    return DiagnosticoCaptura(rango, cromatico, ruido, ruido_rel,
                              detalle_rel, bordes_rel, saturados, tuple(problemas))


def _clahe_luminancia(imagen_bgr: np.ndarray, clahe: cv2.CLAHE) -> np.ndarray:
    """Ecualiza SOLO el canal de luz de Lab; nunca altera el color arbitrariamente."""
    lab = cv2.cvtColor(imagen_bgr, cv2.COLOR_BGR2LAB)
    lab[:, :, 0] = clahe.apply(lab[:, :, 0])
    return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)


def _acuerdo_mascara(m1: Optional[np.ndarray], m2: Optional[np.ndarray]) -> float:
    if m1 is None or m2 is None or m1.shape != m2.shape:
        return 0.
    a = m1 > 0
    b = m2 > 0
    union = int(np.count_nonzero(a | b))
    if union == 0:
        return 0.
    return float(np.count_nonzero(a & b) / union)


class InspectorCalidadRobusto:
    """Inspeccion original + control de captura + verificacion secundaria.

    BIEN/MAL solo se emiten cuando el fotograma aporta informacion suficiente;
    si la calidad de camara o las segmentaciones discrepan, REVISAR se omite
    de la votacion hasta tener imagenes utiles. El producto termina BIEN/MAL
    en seguimiento_banda, que distingue 'inspeccion insuficiente' de defecto.
    """
    def __init__(self, polaridad: str = 'automatica', modelo_calidad: Optional[str] = None):
        self.inspector = InspectorCalidad(polaridad, modelo_calidad)
        # Clip bajo para evitar amplificar demasiado textura y ruido.
        self.clahe = cv2.createCLAHE(clipLimit=1.6, tileGridSize=(4, 4))

    def analizar(self, recorte_bgr: np.ndarray) -> Resultado:
        if recorte_bgr is None or recorte_bgr.size == 0:
            return self.inspector.analizar(recorte_bgr)
        if recorte_bgr.ndim == 2:
            recorte_bgr = cv2.cvtColor(recorte_bgr, cv2.COLOR_GRAY2BGR)
        h, w = recorte_bgr.shape[:2]
        if min(h, w) < 22 or h * w < 1000:
            return self.inspector.analizar(recorte_bgr)

        calidad = diagnosticar_captura(recorte_bgr)
        r = self.inspector.analizar(recorte_bgr)
        r.metricas.update({
            'camara_contraste_luz': calidad.contraste_luminancia,
            'camara_contraste_color': calidad.contraste_cromatico,
            'camara_ruido': calidad.ruido_luminancia,
            'camara_ruido_relativo': calidad.ruido_relativo,
            'camara_detalle_relativo': calidad.detalle_relativo,
            'camara_bordes_relativos': calidad.bordes_relativos,
            'camara_saturacion': calidad.saturacion_fraccion,
            'concordancia_mascaras': -1.0,  # -1 = no se hizo segunda pasada
            'segunda_pasada': 0.0,
        })
        # No alterar la imagen original ni forzarla a escala de grises.
        # Una segunda pasada se reserva para casos sospechosos o imagenes ruidosas.
        # Priorizar eficiencia: una imagen BIEN sin problemas de captura no
        # necesita CLAHE/bilateral ni una segunda inspeccion completa.
        # La segunda pasada se reserva para MAL y REVISAR con indicadores
        # medidos; si la camara ya indica problema, no altera ese diagnostico.
        necesita_comparacion = (
            not calidad.problemas and
            (r.estado == 'MAL' or
             (r.estado == 'REVISAR' and (
                r.metricas.get('pixeles_sospechosos', 0.) > 0. or
                r.metricas.get('indice_arrastre_interno', 0.) > 0. or
                r.metricas.get('snr_contraste', 99.) < 5.5)))
        )
        if necesita_comparacion and not calidad.problemas:
            if calidad.ruido_relativo > .055:
                # Bilateral suave: reduce ruido preservando bordes; NO afila
                # ni reconstruye caracteres ausentes.
                sig = min(30., max(12., 1.6 * calidad.ruido_luminancia))
                variante = cv2.bilateralFilter(recorte_bgr, 5, sig, 2.5)
            else:
                # Contraste local limitado solo en luminancia; la inspeccion
                # original sigue teniendo la prioridad.
                variante = _clahe_luminancia(recorte_bgr, self.clahe)
            r2 = self.inspector.analizar(variante)
            acuerdo = _acuerdo_mascara(r.mascara_tinta, r2.mascara_tinta)
            r.metricas['segunda_pasada'] = 1.0
            r.metricas['concordancia_mascaras'] = acuerdo
            r.metricas['segunda_pasada_mal'] = 1.0 if r2.estado == 'MAL' else 0.0
            # Dos representaciones del mismo trazo deben corroborar una falta
            # grave. Si difieren, no se produce un rechazo por defecto fisico.
            if r2.estado != r.estado or (acuerdo < .30 and r.estado != 'REVISAR'):
                antes = r.estado
                r.estado = 'REVISAR'
                r.motivo = ('Segmentacion inestable entre imagen original y '
                            f'preprocesamiento: {antes} / {r2.estado}')
        # Las marcas ausentes o extremadamente tenues dentro de los trazos
        # no siempre activan los detectores de arrastre/mancha. No convertir
        # una segmentacion limpia automaticamente en una impresion BIEN.
        # Este control NO cuenta letras, ni exige formato o OCR.
        r.metricas['indice_debilitamiento_local'] = 0.0
        r.metricas['tinta_toca_borde_roi'] = 0.0
        if r.estado == 'BIEN' and not calidad.problemas and r.mascara_tinta is not None:
            m = np.uint8(r.mascara_tinta > 0)
            # Si los trazos de tinta llegan a un extremo del recorte puede
            # haberse cortado una parte de la impresion. No asegurar BIEN.
            borde = min(3, max(1, int(round(min(h,w)*.012))))
            densidades = (
                float(np.mean(m[:, :borde])), float(np.mean(m[:, -borde:])),
                float(np.mean(m[:borde, :])), float(np.mean(m[-borde:, :])))
            contacto = max(densidades)
            r.metricas['tinta_toca_borde_roi'] = contacto
            # El contacto debe ser significativo; un punto de ruido aislado
            # no invalida una inspeccion.
            if contacto > .065:
                r.estado = 'REVISAR'
                r.motivo = ('Trazos cerca del limite del recorte; '
                            'no se puede comprobar su integridad completa')
            else:
                debil = detectar_debilitamiento(recorte_bgr, r.mascara_tinta, r.polaridad)
                r.metricas['indice_debilitamiento_local'] = debil.indice
                if debil.posible_debilitamiento:
                    r.estado = 'REVISAR'
                    r.motivo = ('POSIBLE IMPRESION INCOMPLETA: ' + debil.motivo)
                    r.mascara_sospechosa = cv2.bitwise_or(
                        r.mascara_sospechosa,
                        debil.mascara)
                    r.metricas['pixeles_sospechosos'] = float(
                        np.count_nonzero(r.mascara_sospechosa))
        # Barrido de presencia de tinta: detectar franjas anormalmente vacias
        # ENTRE trazos que continuan a ambos lados. No busca caracteres en
        # coordenadas fijas ni verifica la longitud/formato de una fecha.
        r.metricas['indice_continuidad_tinta'] = 0.0
        r.metricas['franjas_continuidad_tinta'] = 0.0
        r.metricas['coincidencias_continuidad'] = 0.0
        r.metricas['continuidad_confirmada'] = 0.0
        if r.mascara_tinta is not None and not calidad.problemas and r.estado != 'MAL':
            continuidad = detectar_barrido_continuidad(recorte_bgr, r.mascara_tinta)
            r.metricas['indice_continuidad_tinta'] = continuidad.indice
            r.metricas['franjas_continuidad_tinta'] = float(len(continuidad.franjas))
            r.metricas['coincidencias_continuidad'] = float(continuidad.coincidencias)
            r.metricas['continuidad_confirmada'] = float(continuidad.confirmada)
            if continuidad.sospechosa:
                r.mascara_sospechosa = cv2.bitwise_or(
                    r.mascara_sospechosa, continuidad.mascara)
                r.metricas['pixeles_sospechosos'] = float(
                    np.count_nonzero(r.mascara_sospechosa))
                if continuidad.confirmada:
                    r.estado = 'MAL'
                    r.motivo = ('POSIBLE IMPRESION BORRADA CONFIRMADA POR BARRIDO: '
                                + continuidad.motivo)
                    r.defectos.append('Perdida de tinta en franja interior')
                    r.puntaje = min(r.puntaje, 25.)
                elif r.estado == 'BIEN':
                    r.estado = 'REVISAR'
                    r.motivo = 'SIN VOTO BUENA: ' + continuidad.motivo
        # Etapa 05 es el mapa PRINCIPAL de geometria. Un borrado puede dejar
        # el fondo limpio y muy pocos caracteres; no interpretarlo como BUENA.
        # Este control localiza restos fragmentados y reglas externas del ROI,
        # sin contar caracteres ni exigir formatos. La mascara aislada genera
        # incertidumbre, no una afirmacion de tinta mala sin foto original.
        r.metricas['indice_auditoria_mascara'] = 0.0
        r.metricas['regiones_auditoria_mascara'] = 0.0
        if r.mascara_tinta is not None and r.estado != 'MAL':
            auditoria = auditar_mascara_tinta(r.mascara_tinta)
            r.metricas['indice_auditoria_mascara'] = auditoria.indice
            r.metricas['regiones_auditoria_mascara'] = float(auditoria.regiones)
            if auditoria.sospecha:
                if r.mascara_sospechosa is None:
                    r.mascara_sospechosa = auditoria.mascara.copy()
                else:
                    r.mascara_sospechosa = cv2.bitwise_or(
                        r.mascara_sospechosa, auditoria.mascara)
                r.metricas['pixeles_sospechosos'] = float(
                    np.count_nonzero(r.mascara_sospechosa))
                if r.estado == 'BIEN' or r.motivo == 'Trazos ambiguos; verificar visualmente':
                    r.estado = 'REVISAR'
                    r.motivo = 'SIN VOTO BUENA | ANALISIS DE MASCARA: ' + auditoria.motivo
        problemas = list(calidad.problemas)
        # Si la tinta ocupa aproximadamente un solo pixel de grosor no hay
        # detalle espacial para buscar pequeños cortes o excesos. No inventar
        # un defecto mediante upscaling/enfoque digital.
        if (min(h, w) < 95 and r.metricas.get('grosor_medio', 999.) < 2.2
                and r.metricas.get('fraccion_tinta', 0.) > .004):
            problemas.append('trazos demasiado finos en pixeles para verificar defectos')
        if problemas:
            # Los filtros no pueden demostrar defectos de tinta cuando la
            # captura misma carece de detalle/contraste fiable.
            r.estado = 'REVISAR'
            r.motivo = 'CAPTURA NO EVALUABLE: ' + '; '.join(problemas)
            r.metricas['camara_captura_no_evaluable'] = 1.0
        else:
            r.metricas['camara_captura_no_evaluable'] = 0.0
        return r
