"""Evidencia de arrastre lineal que cruza los trazos de una fecha.

No es OCR. Opera sobre el recorte de YOLO y la mascara binaria de tinta.
Para evitar confundir caracteres, arrugas y bordes del envase con defectos,
solo considera *varias* crestas largas, aproximadamente paralelas, que se
superponen espacialmente y atraviesan la zona de tinta segmentada.

Los umbrales son de tamizaje y requieren validacion con muestras etiquetadas.
"""
from __future__ import annotations
from dataclasses import dataclass
import cv2
import numpy as np

@dataclass(frozen=True)
class EvidenciaArrastre:
    fuerte: bool
    posible: bool
    indice: float
    longitud_relativa: float
    superposicion_relativa: float
    bandas_paralelas: int
    mascara: np.ndarray
    fraccion_tinta_fuerte: float = 0.


def detectar_arrastre_interno(recorte_bgr: np.ndarray, mascara_tinta: np.ndarray) -> EvidenciaArrastre:
    if recorte_bgr is None or mascara_tinta is None or recorte_bgr.size == 0:
        return EvidenciaArrastre(False, False, 0., 0., 0., 0, np.zeros((0, 0), np.uint8))
    h0, w0 = recorte_bgr.shape[:2]
    out = np.zeros((h0,w0),np.uint8)
    if min(h0,w0) < 34 or h0*w0 < 1800 or mascara_tinta.shape[:2] != (h0,w0):
        return EvidenciaArrastre(False, False, 0., 0., 0., 0, out)
    girado = h0 > w0
    if girado:
        imagen = cv2.rotate(recorte_bgr, cv2.ROTATE_90_CLOCKWISE)
        tinta = cv2.rotate(np.uint8(mascara_tinta > 0), cv2.ROTATE_90_CLOCKWISE)
    else:
        imagen = recorte_bgr
        tinta = np.uint8(mascara_tinta > 0)
    h,w = tinta.shape
    ys,xs = np.where(tinta>0)
    if xs.size < 28:
        return EvidenciaArrastre(False, False, 0., 0., 0., 0, out)
    lo_x,hi_x = int(np.percentile(xs,1)), int(np.percentile(xs,99))
    lo_y,hi_y = int(np.percentile(ys,1)), int(np.percentile(ys,99))
    ink_span = max(1,hi_x-lo_x)
    if ink_span < max(45, w*.22):
        return EvidenciaArrastre(False, False, 0., 0., 0., 0, out)

    # Gradiente vertical alto y horizontal pequeno = borde de una cresta
    # aproximadamente alineada con las lineas de texto. Se estima en original
    # (sin CLAHE ni enfoque, que podrian inventar crestas).
    lab = cv2.cvtColor(imagen, cv2.COLOR_BGR2LAB)
    lum = cv2.GaussianBlur(lab[:,:,0], (3,3), 0.5)
    gx = cv2.Sobel(lum, cv2.CV_32F, 1,0,3)
    gy = cv2.Sobel(lum, cv2.CV_32F, 0,1,3)
    # Umbral dependiente del contraste presente, no de un formato de fecha.
    umbral = float(np.clip(np.percentile(np.abs(gy),95)*.15, 12., 30.))
    crestas = np.uint8((np.abs(gy)>=umbral) & (np.abs(gy)>1.2*np.abs(gx)))
    cierre = max(3, min(7, round(w*.006)))
    crestas = cv2.morphologyEx(crestas,cv2.MORPH_CLOSE,np.ones((1,cierre),np.uint8))
    largo = max(25, min(165, int(round(ink_span*.15))))
    crestas = cv2.morphologyEx(crestas,cv2.MORPH_OPEN,np.ones((1,largo),np.uint8))

    n,etiquetas,stats,cents = cv2.connectedComponentsWithStats(crestas,8)
    grupos=[]
    y_margin=max(4,int(.06*h))
    for i in range(1,n):
        x,y,cw,ch,area = (int(v) for v in stats[i])
        yc = y + ch/2
        # Crestas interiores, no lineas impresas en la etiqueta fuera de la fecha.
        if (cw < max(32,.155*ink_span) or cw > .96*w or
            ch > max(14,.16*h) or area < cw*.6 or
            yc < max(y_margin,lo_y-.08*h) or yc > min(h-y_margin,hi_y+.08*h) or
            x+cw < lo_x+.10*ink_span or x > hi_x-.10*ink_span):
            continue
        grupos.append((x,y,cw,ch,i))

    if len(grupos)<2:
        return EvidenciaArrastre(False, False, 0., 0., 0., len(grupos), out)
    # Emparejar crestas distintas, cercanas y con tramo horizontal compartido;
    # una letra de imprenta con una sola barra larga no debe causar rechazo.
    mejor=(0.,0.,None,None)
    limite_y=max(7,int(.33*h))
    for j,g in enumerate(grupos):
        x,y,cw,ch,i=g
        cy=y+ch/2
        for g2 in grupos[j+1:]:
            x2,y2,cw2,ch2,i2=g2
            cy2=y2+ch2/2
            delta_y=abs(cy-cy2)
            if delta_y < max(4,int(.025*h)) or delta_y > limite_y:
                continue
            inter=max(0,min(x+cw,x2+cw2)-max(x,x2))
            long_frac=max(cw,cw2)/ink_span
            inter_frac=inter/ink_span
            # Ubicacion centrada: hace falta tinta impresa cerca del par.
            a=max(0,min(y,y2)-max(4,int(.04*h)))
            b=min(h,max(y+ch,y2+ch2)+max(4,int(.04*h)))
            xlo=max(0,max(x,x2)-int(.02*w));xhi=min(w,min(x+cw,x2+cw2)+int(.02*w))
            if xhi<=xlo or np.count_nonzero(tinta[a:b,xlo:xhi]) < max(12, .01*(b-a)*(xhi-xlo)):
                continue
            if (inter_frac>=.08 and long_frac>=.23 and
               long_frac+inter_frac > mejor[0]+mejor[1]):
                mejor=(long_frac,inter_frac,g,g2)
    long_frac, inter_frac,g1,g2=mejor
    if g1 is None:
        return EvidenciaArrastre(False,False,0.,0.,0.,len(grupos),out)
    # No marcar cualquier cresta visible; solo las que corroboran el par.
    mascara = np.zeros((h,w),np.uint8)
    xlo=min(g1[0],g2[0]);xhi=max(g1[0]+g1[2],g2[0]+g2[2])
    ylim=min(g1[1],g2[1]);ymax=max(g1[1]+g1[3],g2[1]+g2[3])
    for x,y,cw,ch,idx in grupos:
        if y<=ymax+6 and y+ch>=ylim-6 and x+cw>=xlo and x<=xhi:
            mascara[etiquetas==idx]=255
    # Al menos dos crestas que cubren gran parte del codigo (no OCR).
    # Una raya impresa intencionalmente (p. ej. dos lineas decorativas)
    # tiende a mantenerse en la mascara de tinta FUERTE. Un arrastre tenue
    # incluye principalmente bordes de contraste intermedio, ausentes en ella.
    # Evitar condenar lineas originales de alto contraste por su geometria.
    fraccion_fuerte = float(np.mean(tinta[mascara>0])) if np.any(mascara) else 1.
    es_tenue = fraccion_fuerte < .42
    fuerte = es_tenue and ((long_frac>=.30 and inter_frac>=.15) or
                           (long_frac>=.24 and inter_frac>=.19 and len(grupos)>=3))
    posible = es_tenue and long_frac>=.23 and inter_frac>=.08
    indice = round(float(min(1., .6*long_frac+.7*inter_frac)),4) if posible else 0.
    if not posible:
        mascara[:] = 0
    if girado:
        mascara=cv2.rotate(mascara,cv2.ROTATE_90_COUNTERCLOCKWISE)
    return EvidenciaArrastre(fuerte,posible,indice,float(long_frac),float(inter_frac),len(grupos),mascara,fraccion_fuerte)
