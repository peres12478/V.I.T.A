"""Tests del voto de varias fotos POR PRODUCTO sin depender de una camara/YOLO."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import unittest

from seguimiento_banda import SeguimientoBanda, Observacion


def observacion(estado, x=10, y=30, nitidez=None):
    return Observacion((x, y, x + 110, y + 45), estado, nitidez=nitidez)


def mandar(seguidor, secuencia, paso=.10):
    eventos=[]
    for i, estado in enumerate(secuencia):
        res=seguidor.actualizar([observacion(estado, 10 + i*9)], i*paso,i+1)
        eventos.extend(res.eventos)
    return eventos


class PruebaMayoriaBanda(unittest.TestCase):
    def test_predominan_buenas(self):
        b=SeguimientoBanda(min_buenas=1, objetivo=7)
        eventos=mandar(b,['BIEN','BIEN','MAL','BIEN','BIEN','MAL','BIEN'])
        self.assertEqual(len(eventos),1)
        self.assertEqual(eventos[0].estado,'BIEN')
        self.assertEqual((eventos[0].buenas,eventos[0].malas),(5,2))
        self.assertEqual(eventos[0].cierre,'objetivo')

    def test_predominan_malas(self):
        b=SeguimientoBanda(min_buenas=1, objetivo=7)
        eventos=mandar(b,['MAL','MAL','BIEN','MAL','BIEN','MAL','BIEN'])
        self.assertEqual(len(eventos),1)
        self.assertEqual(eventos[0].estado,'MAL')
        self.assertIn('MAYORIA MALA',eventos[0].motivo)

    def test_empate_se_rechaza(self):
        b=SeguimientoBanda(min_buenas=1, objetivo=7)
        eventos=mandar(b,['BIEN','MAL','BIEN','MAL'])
        self.assertFalse(eventos)
        b.actualizar([], .50, 9)
        b.actualizar([], .78, 10)
        eventos=b.actualizar([], 1.05, 12).eventos
        self.assertEqual(len(eventos),1)
        self.assertEqual(eventos[0].estado,'MAL')
        self.assertIn('EMPATE',eventos[0].motivo)

    def test_ambigua_no_cuenta_como_mala(self):
        b=SeguimientoBanda(min_buenas=1, objetivo=7)
        secuencia=['BIEN','REVISAR','BIEN','MAL','REVISAR','BIEN']
        self.assertFalse(mandar(b,secuencia))
        b.actualizar([],.65,13)
        b.actualizar([],.85,14)
        ev=b.actualizar([],1.2,15).eventos[0]
        self.assertEqual(ev.estado,'BIEN')
        self.assertIn('MAYORIA BUENA',ev.motivo)
        self.assertEqual((ev.buenas,ev.malas),(3,1))
        self.assertTrue(1 <= ev.ambiguas <= 2)
        self.assertGreaterEqual(ev.dudosas_ignoradas, 0)
        self.assertEqual(ev.validas,4)

    def test_insuficiente_es_rechazo_preventivo_no_defecto_confirmado(self):
        b=SeguimientoBanda(min_buenas=1, objetivo=7)
        mandar(b,['REVISAR','REVISAR','REVISAR'])
        b.actualizar([],.50,13)
        b.actualizar([],.70,14)
        ev=b.actualizar([],.95,15).eventos[0]
        self.assertEqual(ev.estado,'MAL')
        self.assertIn('SIN VOTOS EVALUABLES',ev.motivo)
        self.assertEqual(ev.malas,0)

    def test_demasiadas_ambiguas_no_anulan_una_mayoria_buena(self):
        b=SeguimientoBanda(min_buenas=1, objetivo=7, min_validas=3, proporcion_minima=.60)
        mandar(b,['BIEN','REVISAR','REVISAR','BIEN','REVISAR','BIEN'])
        b.actualizar([],.65,13)
        b.actualizar([],.85,14)
        ev=b.actualizar([],1.2,16).eventos[0]
        self.assertEqual(ev.estado,'BIEN')
        self.assertIn('MAYORIA BUENA',ev.motivo)
        self.assertIn('AVISO DE CONFIABILIDAD',ev.motivo)
        self.assertEqual((ev.buenas, ev.malas, ev.ambiguas),(3,0,3))

    def test_no_duplica_resultado_de_un_producto(self):
        b=SeguimientoBanda(min_buenas=1, objetivo=3,min_validas=2)
        eventos=mandar(b,['BIEN']*9)
        self.assertEqual(len(eventos),1)
        self.assertEqual(len(b.actualizar([],2.0,10).eventos),0)
        self.assertEqual(len(b.cerrar(2.1,11)),0)

    def test_dos_productos_simultaneos_no_comparten_votos(self):
        b=SeguimientoBanda(min_buenas=1, objetivo=5,min_validas=3)
        eventos=[]
        for i in range(5):
            salida=b.actualizar([observacion('BIEN', 20+i*7),
                                 observacion('MAL',400+i*6)], .1*i,i+1)
            eventos+=salida.eventos
        self.assertEqual(len(eventos),2)
        self.assertEqual({ev.estado for ev in eventos},{'BIEN','MAL'})
        self.assertNotEqual(eventos[0].id,eventos[1].id)
        self.assertEqual({ev.validas for ev in eventos},{5})

    def test_dos_productos_separados_tienen_diferentes_id(self):
        b=SeguimientoBanda(min_buenas=1, objetivo=3,min_validas=3)
        eventos=mandar(b,['BIEN']*3)
        b.actualizar([],.51,4)
        b.actualizar([],.71,5)
        b.actualizar([],.81,6)
        eventos+=b.actualizar([observacion('MAL',10)],.9,6).eventos
        eventos+=b.actualizar([observacion('MAL',18)],1.,7).eventos
        eventos+=b.actualizar([observacion('MAL',26)],1.1,8).eventos
        self.assertEqual(len(eventos),2)
        self.assertEqual([ev.estado for ev in eventos],['BIEN','MAL'])
        self.assertEqual([ev.id for ev in eventos],[1,2])

    def test_desaparicion_temporal_no_crea_nuevo_producto(self):
        b=SeguimientoBanda(min_buenas=1, objetivo=3,min_validas=2,max_sin_ver=5)
        ids=[]
        for i,estado in enumerate(['BIEN','BIEN','BIEN']):
            salida=b.actualizar([observacion(estado,10+i*10)],i*.1,i+1)
            ids.append(salida.asignaciones[0][0])
            if i == 0:
                self.assertEqual(len(b.actualizar([], .05,100).eventos),0)
        self.assertEqual(ids,[1,1,1])

    def test_intervalo_evitaria_contar_fotogramas_casi_iguales(self):
        b=SeguimientoBanda(min_buenas=1, objetivo=3,min_validas=2,intervalo_s=.1)
        for i in range(5):
            b.actualizar([observacion('BIEN',10+i)],i*.02,i+1)
        self.assertEqual(b.pistas[1].validas,1)
        b.actualizar([observacion('BIEN',16)],.12,6)
        self.assertEqual(b.pistas[1].validas,2)

    def test_nitidez_descarta_foto_si_esta_activada(self):
        b=SeguimientoBanda(min_buenas=1, objetivo=3,min_validas=2,min_nitidez=40.)
        entradas=[observacion('MAL',10,nitidez=10),
                  observacion('BIEN',20,nitidez=140),
                  observacion('BIEN',30,nitidez=110)]
        eventos=[]
        for i,obs in enumerate(entradas):
            eventos += b.actualizar([obs],i*.1,i+1).eventos
        self.assertEqual(len(eventos),1)
        ev=eventos[0]
        self.assertEqual(ev.estado,'BIEN')
        self.assertEqual(ev.desenfocadas,1)
        self.assertEqual(ev.malas,0)

    def test_no_devuelve_tercer_estado_final(self):
        estados=['BIEN','MAL','REVISAR']
        for k in range(5):
            b=SeguimientoBanda(min_buenas=1, objetivo=7)
            mandar(b, [estados[(i+k)%3] for i in range(6)])
            eventos=b.cerrar(.8,10)
            self.assertEqual(len(eventos),1)
            self.assertIn(eventos[0].estado,('BIEN','MAL'))

    def test_tres_inciertas_cierran_una_vez_sin_votos(self):
        b=SeguimientoBanda(min_buenas=1, objetivo=3,min_validas=2,max_muestras=4)
        eventos=mandar(b,['REVISAR']*7)
        self.assertEqual(len(eventos),1)
        self.assertEqual(eventos[0].cierre,'objetivo')
        self.assertEqual(eventos[0].estado,'MAL')
        self.assertEqual(eventos[0].total,3)
        self.assertEqual(eventos[0].ambiguas,3)


if __name__ == '__main__':
    unittest.main()
