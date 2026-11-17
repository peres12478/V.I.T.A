"""Entrenamiento opcional SUPERVISADO sobre zonas de fecha ya recortadas.

Estructura:
  datos_calidad/BIEN/lote_A/a.jpg
  datos_calidad/MAL/lote_A/b.jpg
  datos_calidad/BIEN/lote_B/c.jpg
  datos_calidad/MAL/lote_B/d.jpg

Agrupar por lote/campana/material evita fuga de fotogramas casi iguales.
Necesita: scikit-learn y joblib; etiquetas MANUALES, no presuntas.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import sys
import cv2
import numpy as np
from calidad_impresion import InspectorCalidad, FEATURE_NAMES


def main():
    parser=argparse.ArgumentParser(description='Entrenar clasificador de defectos (requiere fotos etiquetadas)')
    parser.add_argument('--datos',type=Path,required=True)
    parser.add_argument('--salida',type=Path,default=Path('clasificador_calidad.joblib'))
    parser.add_argument('--minimo',type=int,default=30,help='Minimo de recortes etiquetados por clase')
    args=parser.parse_args()
    try:
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.model_selection import train_test_split, GroupShuffleSplit
        from sklearn.metrics import classification_report,confusion_matrix
        import joblib
    except ImportError:
        raise SystemExit('Instala: python -m pip install scikit-learn joblib')
    inspector=InspectorCalidad()
    features=[]; labels=[]; grupos=[]
    for categoria,y in (('BIEN',0),('MAL',1)):
        ruta=args.datos/categoria
        if not ruta.is_dir(): raise SystemExit(f'Falta la carpeta {ruta}')
        fotos=[p for p in ruta.rglob('*') if p.suffix.lower() in ('.jpg','.jpeg','.png','.bmp')]
        if len(fotos)<args.minimo:
            raise SystemExit(f'{categoria}: {len(fotos)} fotos. Minimo: {args.minimo}; no entrenes con tan pocas.')
        for path in fotos:
            im=cv2.imread(str(path))
            if im is None:continue
            r=inspector.analizar(im)
            if not r.metricas or len(r.metricas)<len(FEATURE_NAMES):continue
            features.append(r.caracteristicas());labels.append(y)
            relative=path.relative_to(ruta)
            grupos.append(relative.parts[0] if len(relative.parts)>1 else path.stem)
    X=np.array(features,dtype=np.float32);y=np.array(labels,dtype=np.int32)
    if len(set(y.tolist()))<2: raise SystemExit('Necesitas al menos dos clases verificadas.')
    # Grupo compuesto por lote/substrato: No se deben mezclar imagenes
    # del mismo lote entre desarrollo y prueba.
    groups=np.array(grupos)
    group_to_labels={g:set(y[groups==g].tolist()) for g in np.unique(groups)}
    usable_groups=sum(1 for g in group_to_labels if len(group_to_labels[g])>0)
    if usable_groups>=8 and all(sum(int(i in labelset) for labelset in group_to_labels.values())>=3 for i in [0,1]):
        splitter=GroupShuffleSplit(test_size=.25,n_splits=1,random_state=42)
        tr,te=next(splitter.split(X,y,groups=groups))
        if len(set(y[tr].tolist()))<2 or len(set(y[te].tolist()))<2:
            raise SystemExit('La particion por lote no contiene ambas clases. Agrega mas lotes.')
        print('Validacion POR LOTE (sin mezcla de tomas del mismo lote)')
    else:
        raise SystemExit('Se necesitan >=8 lotes independientes (subcarpetas) y >=3 por clase. Evitamos validar con fotos casi iguales.')
    clf=RandomForestClassifier(n_estimators=300,max_depth=8,min_samples_leaf=3,class_weight='balanced',random_state=42,n_jobs=-1)
    clf.fit(X[tr],y[tr])
    pred=clf.predict(X[te])
    print(classification_report(y[te],pred,zero_division=0,target_names=['BIEN','MAL']))
    print('Matriz de confusion:\n',confusion_matrix(y[te],pred,labels=[0,1]))
    # El modelo para produccion se reentrena con todos los datos etiquetados;
    # las metricas previas provienen solo del conjunto retenido.
    clf.fit(X,y)
    args.salida.parent.mkdir(exist_ok=True,parents=True)
    joblib.dump({'feature_names':FEATURE_NAMES,'clasificador':clf},args.salida)
    print('Modelo guardado:',args.salida)
    print('Advertencia: no usar para rechazo automatico sin pruebas en productos nunca vistos.')

if __name__=='__main__':main()
