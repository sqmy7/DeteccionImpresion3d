# Datos reales del modelo (lo que hay en este equipo)

Hecho el 2026-10-08 con el trabajo 43 ya cerrado. El prompt `prompt_datos_reales_modelo.md` **no está** en el
repositorio ni en la carpeta de salidas, así que se siguieron las prioridades de la cola. Nada se inventó:
lo que no está en este equipo se dice.

## Qué hay y qué falta

| Elemento | Estado en este equipo |
|---|---|
| Pesos desplegados `inference/models/best_fp32.onnx` (37,9 MB) y `best_int8.onnx` (9,9 MB) | **Hay** |
| Métricas guardadas (`best_fp32.metrics.json`, `best_int8.metrics.json`) y config de entrenamiento (`train_config.yaml`) | **Hay** |
| `args.yaml` y `results.csv` del entrenamiento | **No están** (se entrenó en Colab; buscados en Descargas, Escritorio, Documentos y OneDrive) |
| Pesos `.pt`, matriz de confusión, curvas | **No están** |
| Dataset (imágenes y etiquetas) | **No está**: `inference/training/datasets/processed/` solo trae `.gitkeep` |
| Evaluación FP32 completa sobre el conjunto de prueba (841 imágenes) | **No se pudo** (no hay dataset); no se corrió |

Sin `args.yaml` no se puede confirmar que los hiperparámetros de `train_config.yaml` fueran los usados; es lo
que el cuaderno lee, no un registro de lo que corrió.

## Tamaño del modelo (medido sobre el archivo, `backend/scripts/onnx_stats.py`)

| | `best_fp32.onnx` | `best_int8.onnx` |
|---|---|---|
| Parámetros (elementos de los *initializers*) | **9.457.164** | 9.457.862 (mismos pesos, cuantizados) |
| GFLOPs a 640×640 (2 × MAC de las Conv) | **≈ 21,3** (parcial: faltan 2 MatMul de atención, que no tienen peso fijo) | no calculado (el grafo cuantizado usa `QLinearConv`) |
| Nodos | 320 | 843 |

- El contador se validó con el modelo `yolo11s_dummy.onnx` (80 clases): da 9,47 M parámetros y 21,47 GFLOPs,
  frente a los ~9,4 M y 21,5 GFLOPs que publica Ultralytics para YOLO11s. Con 6 clases la cabeza es más chica,
  de ahí 21,3.
- "Parámetros" cuenta todos los *initializers* del grafo: incluye unas pocas constantes del exportador (formas,
  pasos), y las capas Conv ya vienen fusionadas con la normalización. Es el modelo desplegado, no el de
  entrenamiento.
- El resultado crudo está en `docs/laboratorio/onnx_stats.json`.

## Cómo se usa en producción (de `inference/model.py` y `inference/config.py`)

- ONNX Runtime en CPU, **1 hilo** (`intra_op_num_threads`), una inferencia por capa.
- Preprocesamiento: **estiramiento** a 640×640 (no *letterbox*), BGR → RGB, /255.
- Umbral de confianza **0,25** (`confidence_threshold`), el mismo con que se calibró.
- Posproceso: se toma la clase de mayor puntaje de cada predicción (una clase por caja) y se aplica
  `cv2.dnn.NMSBoxes` con **IoU 0,45 independiente de la clase**: una caja de otra clase que se solape más de 0,45
  con otra de mayor puntaje se descarta. Ultralytics hace NMS por clase.
- Las cajas se guardan normalizadas respecto de la región que vio el modelo (y desde 2026-10-08 se guarda también
  ese cuadro y la región, para ubicarlas en la cama).

## Métricas guardadas y qué miden

- `best_fp32.metrics.json` (calibración del 2026-09-18, **la misma tubería que producción**: estiramiento, NMS
  agnóstico de clase, umbral 0,25; 841 imágenes, 1.312 instancias, 157 imágenes sin objetos). A nivel imagen:
  general precisión 0,997 y recall 0,921; spaghetti 0,963 / 0,975; warping 0,988 / 0,988; stringing 0,977 / 0,959;
  layer_shift 1,0 / 1,0; under_extrusion 0,919 / 0,685; blob_over_extrusion 0,562 / 0,529 (solo 17 imágenes).
- `best_int8.metrics.json` (validación del 2026-09-18 con `val()` de Ultralytics, que usa *letterbox* y NMS por
  clase): mAP50 0,676 y mAP50-95 0,378 en general; por clase, mAP50 spaghetti 0,892, warping 0,895, stringing
  0,721, layer_shift 0,964, under_extrusion 0,356, blob_over_extrusion 0,227.
- **Las dos series no son comparables entre sí**: una es del modelo FP32 con la tubería de producción a nivel
  imagen; la otra es del INT8 con la tubería de Ultralytics a nivel caja (mAP). Además, el INT8 **no** es el
  desplegado.
- Todas se midieron sobre fotos de Roboflow Universe; **ninguna sobre imágenes de la C922 con la Hi** (todavía no
  hay detecciones reales: `capture` estuvo apagado).

## Lo que haría falta para cerrar esto

1. Copiar a este equipo `args.yaml` y `results.csv` de la corrida de Colab (y, si se quiere, `best.pt`).
2. Tener el conjunto de prueba procesado para repetir la calibración del FP32 con pocos hilos.
3. Reunir detecciones reales con la C922 y etiquetarlas: es lo único que dirá cuánto se parece el rendimiento
   real al de las métricas.
