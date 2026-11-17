"""Pruebas del lector de cuadros recientes y la escritura de evidencia no bloqueante."""
from __future__ import annotations
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from camara_buffer import CapturaReciente
from evidencia_en_cola import EvidenciasEnCola


class CamaraLentaFalsa:
    def __init__(self): self.n=0;self.closed=False
    def read(self):
        if self.closed:return False,None
        self.n+=1
        time.sleep(.014)
        return True,np.full((18,26,3),self.n%250,np.uint8)
    def release(self):self.closed=True


class TestRendimientoEscritorio(unittest.TestCase):
    def test_captura_omite_buffers_antiguos(self):
        cam=CamaraLentaFalsa()
        lector=CapturaReciente(cam,pausa_minima=.002)
        try:
            item=lector.esperar_nuevo(0,timeout=.5)
            self.assertIsNotNone(item)
            seq,frame,t=item
            time.sleep(.11)
            nuevo=lector.esperar_nuevo(seq,timeout=.5)
            self.assertIsNotNone(nuevo)
            self.assertGreater(nuevo[0],seq+2)
            self.assertGreater(nuevo[2],t)
            self.assertEqual(frame.shape,(18,26,3))
            self.assertGreater(lector.estadisticas(seq)['sin_procesar'],0)
        finally:
            lector.cerrar();cam.release()

    def test_evidencias_en_cola_se_vacian_en_cierre(self):
        with tempfile.TemporaryDirectory() as td:
            guardador=EvidenciasEnCola(max_pendientes=4)
            class R:
                estado='BIEN';motivo='CONTROL';metricas={'snr':5.}
                mascara_tinta=np.zeros((30,40),np.uint8)
                mascara_sospechosa=np.zeros((30,40),np.uint8)
            roi=np.full((30,40,3),155,np.uint8)
            guardador.agregar(Path(td),1,1,roi,R())
            guardador.cerrar()
            self.assertFalse(guardador.errores)
            archivos=list(Path(td).rglob('*'))
            self.assertTrue(any(x.suffix.lower()=='.png' for x in archivos))
            self.assertTrue(any(x.suffix.lower()=='.jsonl' for x in archivos))


if __name__=='__main__':unittest.main()
