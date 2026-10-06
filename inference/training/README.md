# Entrenamiento del modelo (Colab)

Todo lo automatizable vive en `colab_train.ipynb` y en los scripts de `scripts/`. Esto es
solo la parte manual - lo que te toca hacer a vos antes de correr el notebook, una sola vez
(salvo que indique lo contrario).

## 1. Cuenta de Roboflow

1. Creá una cuenta gratuita en [roboflow.com](https://roboflow.com) si no tenés una.
2. Andá a **Settings → API Keys** y copiá tu API key privada (el notebook te la va a pedir,
   no hace falta pegarla en ningún archivo).

Ya hay 3 datasets reales confirmados y cargados en el notebook (workspace
`samuel-rodriguez-2vtvz`), cubriendo entre los tres nuestras 6 clases - no hace falta buscar
nada para arrancar:

| # | Dataset | Proyecto | Imágenes | Clases |
|---|---|---|---|---|
| 1 | "3D PRINT DEFECT DETECTION" (RVM Detection) | `3d-print-defect-detection-6fcmi-drylp` (v1) | 3612 | blobs (1119), crack (713), Layer_shifting (629), spaghetti (2042), stringing (1924), Warping (805) |
| 2 | "3d print fail detection" | `3d-print-fail-detection-jckut` (v1) | 1002 | 3D-print-fail-detection (0 anotaciones), crack, spaghetti (108), stringing (672) |
| 3 | "Under Extrusion" | `under-extrusion-pf0uy-nlyil` (v1) | 999 | Under Extrusion (1414) |

Ojo: la interfaz de Roboflow llegó a mostrar los nombres del dataset 1 traducidos al español en
algún momento, pero los nombres reales de clase (los que están en su `data.yaml`, y los que
importan para el mapeo) son los de la tabla, en inglés. El dataset 3 usa "Under Extrusion" con
espacio, no guión bajo - también contemplado en el mapeo.

El mapeo de estas clases a nuestra taxonomía ya está confirmado y cargado en
`MAPPINGS['roboflow_generic']` (`scripts/convert_to_yolo.py`). El matching es case-insensitive,
así que `Layer_shifting`/`Warping`/`Under Extrusion` con mayúsculas matchean igual sin nada
especial. `crack` y `3D-print-fail-detection` quedan sin mapear a propósito (no corresponden a
ninguna de nuestras 6 clases).

### Cobertura de clases por dataset

Para el informe: de dónde sale cada una de nuestras 6 clases.

| Nuestra clase | Fuente | Instancias |
|---|---|---|
| spaghetti | dataset 1 (2042) + dataset 2 (108) | 2150 |
| warping | dataset 1 (Warping) | 805 |
| stringing | dataset 1 (1924) + dataset 2 (672) | 2596 |
| layer_shift | dataset 1 (Layer_shifting) | 629 |
| under_extrusion | dataset 3 (Under Extrusion) | 1414 |
| blob_over_extrusion | dataset 1 (blobs) | 1119 |

Las 6 clases tienen un volumen de anotaciones considerable. `stringing` y `spaghetti` son las más
representadas; `layer_shift` y `warping` son las más chicas en cantidad relativa. **Ojo: el volumen
de anotaciones no garantizó buen resultado** - `blob_over_extrusion`, con 1119 anotaciones, es la
clase más débil del modelo (ver "Limitaciones conocidas" al final).

Si más adelante querés sumar más datasets (recomendado para tener más diversidad de
fuentes/cámaras/impresoras), buscá en [Roboflow Universe](https://universe.roboflow.com) con
términos como `3d print defect`, `spaghetti detection`, `stringing detection`,
`print failure detection`, `layer shift`. Para cada uno que encuentres, anotá su **workspace**,
**project** y **version** - salen de la URL del dataset en Universe, o del snippet de descarga
que Roboflow te da si tocás "Download this Dataset" → "YOLOv8" → "show download code" - y
agregalo al notebook con el mismo patrón que los 3 ya cargados.

No hace falta descargar nada a mano: el notebook usa el paquete `roboflow` para bajar los
datasets, directamente al **disco local de Colab** (no a Drive - ver sección 2).

## 2. Subir `inference/training/` a Google Drive

Colab resetea el entorno entre sesiones, así que lo que tiene que sobrevivir entre sesiones
vive en Drive. Pero **Drive es muy lento para I/O de muchos archivos chicos** (cada operación de
archivo tiene latencia de red: con ~11.000 imágenes + labels, copiarlos uno por uno tarda más de
una hora), así que el notebook reparte los roles:

| Dónde | Qué |
|---|---|
| **Drive** | Solo entradas livianas (`scripts/`, `configs/`, `datasets/dataset.yaml`) y resultados finales a persistir (`persisted/`: el dataset procesado empaquetado en **un solo** `processed.tar`, los pesos `best.pt` y el `.onnx`) |
| **Disco local de Colab** (`/content/local_work/`) | Todo el trabajo pesado: descarga, conversión, split y entrenamiento (`raw/`, `interim/`, `processed/`, `runs/`) - minutos en vez de horas |

Consecuencia: si la sesión de Colab se corta a mitad de camino, se pierde lo que no se haya
persistido todavía a Drive. El notebook persiste dos cosas a propósito: el dataset procesado
(justo después del split, celda "Persistir a Drive") y los pesos entrenados (justo después del
entrenamiento).

1. Subí la carpeta completa `inference/training/` (tal como está en tu repo, con `scripts/`,
   `configs/`, `datasets/dataset.yaml`, etc.) a tu Google Drive, por ejemplo a:
   `MyDrive/DeteccionImpresion3d/inference/training/`
2. Si la subís a otra ruta, actualizá `DRIVE_PROJECT_DIR` en la celda de setup del notebook.

No hace falta subir `datasets/raw/` ni `datasets/processed/` con contenido - el notebook los
genera solo, en disco local. Sí asegurate de subir `scripts/`, `configs/train_config.yaml` y
`datasets/dataset.yaml`.

**Si ya corriste una versión anterior del notebook** (la que escribía todo directo en Drive) y
quedaron carpetas `datasets/raw/`, `datasets/interim/`, `datasets/processed/` o `runs/` a medio
llenar en Drive: ya no se usan. Borralas desde la web de Drive (mover la carpeta entera a la
papelera es una sola operación) - no desde Colab, donde borrar miles de archivos uno por uno
tiene la misma lentitud que copiarlos.

## 3. Subir y correr el notebook en Colab

1. Andá a [colab.research.google.com](https://colab.research.google.com) → **Subir** → elegí
   `colab_train.ipynb` (o subilo directo a Drive y abrilo con doble click - Colab lo reconoce).
2. **Activá GPU**: menú **Entorno de ejecución → Cambiar tipo de entorno de ejecución →
   Acelerador por hardware → GPU** (T4 alcanza). Sin esto el entrenamiento es horas en vez de
   minutos.
3. Corré las celdas en orden, de arriba hacia abajo. La primera te va a pedir autorizar el
   montaje de Google Drive (aceptá el popup).
4. En la sección de descarga de datasets solo vas a tener que pegar tu API key de Roboflow
   cuando te la pida (queda solo en memoria de esa sesión) - los 3 datasets ya están cargados
   con sus datos reales, no hay placeholders que reemplazar para arrancar.
5. El mapeo de los 3 datasets ya está confirmado y cargado - no hace falta tocar
   `convert_to_yolo.py` para arrancar. Si en el futuro sumás otro dataset, revisá su
   `data.yaml` real y extendé `MAPPINGS['roboflow_generic']` antes de convertirlo (mapeado a
   una de nuestras 6 clases, o a `None` si no corresponde a ninguna) - una clase sin mapeo se
   descarta con un warning en vez de mapearse mal.
6. **Sesión nueva** (Colab se reseteó pero ya habías procesado el dataset antes): corré la celda
   "2b. Restaurar el dataset ya procesado" y saltá directo a la celda que genera
   `dataset.runtime.yaml`, sin descargar ni convertir nada de nuevo - restaurar es copiar un
   solo archivo de Drive y descomprimirlo en local.
7. El resto (bakeoff, entrenamiento final, validación, export) corre solo. Andá leyendo las
   celdas de markdown, explican qué hace cada bloque.

## 4. Reemplazar el modelo

Al final del notebook se descargan dos archivos: `best_fp32.onnx` y `best_int8.onnx` (ambos quedan además
en Drive, en `persisted/`). **Ultralytics borra el FP32 al exportar el INT8**, por eso el notebook copia el
FP32 antes de cuantizar y verifica por md5 que los dos archivos sean distintos: en una ocasión el "FP32" que
llegó al repo era una copia byte a byte del INT8.

- Copialo a `inference/models/` **con su propio nombre** y apuntá el worker a él con
  `onnx_filename` en `inference/config.py` (o la variable de entorno `ONNX_FILENAME`), en vez de
  pisar `yolo11s_dummy.onnx`: un archivo llamado "dummy" que contiene el modelo real es
  engañoso, y sobrescribirlo es irreversible. Hoy apunta a `best_fp32.onnx`.
- **Nombre de versión**: cada modelo queda registrado en `model_versions` bajo el nombre de
  `onnx_version_name` (`ONNX_VERSION_NAME`), hoy `yolo11s-trained-v1-fp32`. **Cambialo cada vez
  que reemplaces el `.onnx` por un modelo reentrenado** - si reusás el nombre, las detecciones
  nuevas se atribuyen a la fila de la versión vieja. (El worker solo detecta el caso en que
  cambió la lista de clases; no puede detectar un reentrenamiento con las mismas 6 clases.)
- **Las clases salen del propio modelo**: el worker lee los nombres de clase de la metadata del
  `.onnx` (Ultralytics los embebe) y falla al arrancar, con un mensaje claro, si faltan o si no
  coinciden con los canales de salida. Ya no hay ninguna lista de clases hardcodeada ni mapeo
  `class_id % 6` en `inference/model.py`.
- **Métricas (mAP por clase)**: no se pueden leer del `.onnx` - Ultralytics solo embebe los
  argumentos del *export*, no los resultados de la validación. Para guardarlas en
  `model_versions.metrics`, poné un JSON con el resultado de la validación de Colab al lado del
  modelo, con el mismo nombre + `.metrics.json` (por ejemplo
  `inference/models/best_int8.metrics.json`), y reiniciá el worker: lo lee al arrancar y
  actualiza la fila. Si no existe, `metrics` queda en `NULL`.

## 5. Calibrar el umbral de confianza

`CONFIDENCE_THRESHOLD` (hoy 0.20 en `inference/config.py`) se eligió con unas pocas fotos, no con
datos de validación. La celda **8c** del notebook lo calibra sobre el **test set completo**: corre
`scripts/calibrate_thresholds.py` y produce, por clase y para umbrales de 0.05 a 0.70, TP/FP/FN,
precisión, recall y F1 (por instancia, IoU >= 0.5) y precisión/recall a **nivel imagen** ("¿se marcó
esta clase en el frame?", que es lo que usan `has_defect` y la alerta de atasco). Salida en Drive:
`persisted/calibration/<nombre del modelo>/threshold_calibration.{csv,json,png}` (una carpeta por modelo, así se pueden comparar FP32 e INT8 con la misma celda).

- **Evalúa lo que se despliega**: el `.onnx` INT8 con el pre/postprocesado del worker (resize directo,
  NMS agnóstico a la clase IoU 0.45) y, por defecto, con la re-codificación JPEG que hace `capture`.
  No usa `val()` de Ultralytics (letterbox + NMS por clase), así que sus números pueden diferir un poco
  de los de la sección 7. Si cambiás el pre/postprocesado de `inference/model.py`, cambialo también acá.
- **Cómo leer la tabla final**: para pisos de precisión de 0.6 a 0.9 muestra, por clase, el umbral **más
  bajo que alcanza el piso y lo mantiene en todos los umbrales más altos** (con pocas instancias la curva
  de precisión es irregular; el "más bajo con P >= piso" a secas podría ser un valle con suerte) y el
  recall que queda ahí. Se muestra a nivel instancia y a nivel imagen; `unreachable` = ningún umbral
  cumple el piso. Con eso se decide un umbral global o por clase. También imprime el umbral de mejor F1.
- **Etiquetas de segmentación / corruptas**: el script sigue las reglas de Ultralytics. Un `.txt` solo de
  polígonos se convierte a la caja que los encierra (descartarlos dejaría defectos reales sin ground truth y
  contaría como falsos positivos las detecciones correctas); un `.txt` que mezcla polígonos y cajas, o está
  malformado, excluye la imagen completa con un warning. Las excluidas quedan listadas en el JSON
  (`meta.excluded_labels`), y si son más del 5% (`--max-excluded-fraction`) el script aborta.
- **Ojo con las clases con pocas instancias** en el test (`blob_over_extrusion` lo es): la tabla
  avisa cuando hay menos de 50 y sus curvas son ruidosas.
- **`under_extrusion` es especial**: alimenta la alerta crítica de atasco (3 capas seguidas). Para esa
  clase conviene un piso de precisión alto aunque cueste recall.
- Aplicar el resultado: hoy el umbral es global (`CONFIDENCE_THRESHOLD`). Los umbrales por clase **no
  están implementados** en el worker; se agregan cuando las curvas muestren que un umbral global no
  alcanza.
- Se puede correr también fuera de Colab: `python scripts/calibrate_thresholds.py --model ... --images
  datasets/processed/images/test --labels datasets/processed/labels/test`.

### Diagnosticar una clase débil (celda 8d)

`scripts/inspect_false_positives.py` (celda **8d**) explica *por qué* una clase falla al umbral desplegado: clasifica
cada falsa alarma (`duplicate`, `mislocalized`, `confused_with:X`, `unannotated`) y cada caja real perdida
(`below_threshold`, `predicted_as:X`, `mislocalized`, `not_detected`), imprime el tamaño mediano de lo encontrado vs.
lo perdido y guarda imágenes anotadas + montajes en `persisted/diagnosis/<clase>/`. Es el paso previo a decidir
si una clase necesita más datos, mejores etiquetas, negativos, mayor resolución u otro remedio. Las cajas
`unannotated` pueden ser fondo **o defectos reales sin etiquetar**: solo mirando las imágenes se distingue.

### Resultado de la calibración (cerrada)

Calibración sobre el test set completo (841 imágenes, 157 sin anotaciones) del **FP32 desplegado**
(`best_fp32.onnx`, versión `yolo11s-trained-v1-fp32`), con el pre/postprocesado del worker. **Decisión: umbral
global `CONFIDENCE_THRESHOLD = 0.25`, sin umbrales por clase** (la ganancia esperada no justifica la complejidad
extra en el worker). Los números a ese umbral, a **nivel imagen** (se guardan también en
`model_versions.metrics` y en `inference/models/best_fp32.metrics.json`):

| Clase | Precisión | Recall |
|---|---|---|
| **General (`has_defect`)** | **0.997** | **0.921** |
| spaghetti | 0.963 | 0.975 |
| warping | 0.988 | 0.988 |
| stringing | 0.977 | 0.959 |
| layer_shift | 1.000 | 1.000 |
| under_extrusion | 0.919 | 0.685 |
| blob_over_extrusion | **0.562** | 0.529 |

El piso de precisión del 90% (la prioridad del proyecto) se cumple en el general y en 5 de las 6 clases.

## Limitaciones conocidas

- **`blob_over_extrusion` es la clase débil del modelo y no alcanza el 90% de precisión a ningún umbral** (a nivel
  imagen: precisión 0.562 y recall 0.529 a 0.25; a nivel caja: 0.468 y 0.152; en la validación de Ultralytics mAP50
  0.227). **El umbral no es la palanca**: subirlo solo sacrifica recall. Diagnóstico completo, causa más probable y
  decisión en la subsección siguiente. **En el sistema se trata como clase informativa** (se muestra, marcada como
  menos confiable, y no cuenta como defecto confirmado ni genera alertas): ver "Cómo se refleja en el sistema".
- **`under_extrusion`**: precisión 0.919 (justo sobre el piso) pero recall 0.685; se pierde cerca de 1 de cada 3
  frames con la clase. Alimenta la alerta de atasco de 3 capas consecutivas, que es más tolerante a falsos negativos
  aislados que a falsos positivos.
- **Un solo umbral global**: los umbrales por clase no están implementados en el worker (decisión explícita, ver
  arriba). Si en el futuro se reentrena, volver a correr la celda 8c antes de confiar en 0.25.
- **La calibración es sobre el test set de estos 3 datasets** (fotos de Roboflow Universe); no hay medición con la
  cámara e impresora reales del proyecto. Es la validación pendiente antes de dar por buenos estos números en
  producción.

### Diagnóstico de `blob_over_extrusion` (celda 8d)

Corrida de `inspect_false_positives.py` sobre las 841 imágenes del test set (17 contienen la clase; 2 etiquetas
inutilizables excluidas), con el FP32 desplegado al umbral 0.25, **a nivel caja** (por eso difiere de la tabla a nivel
imagen de arriba). Respaldo: `diagnosis/blob_over_extrusion.diagnosis_summary.json` (transcrito de lo impreso por la
celda; el `diagnosis.json` original, con las listas de imágenes, está en Drive `persisted/diagnosis/blob_over_extrusion/`).

| | Cajas | Detalle |
|---|---|---|
| Aciertos (TP) | 22 | precisión 0.468 = 22 / (22 + 25) |
| Falsas alarmas (FP) | 25 | 21 `unannotated` (84%), 4 `mislocalized`, **0 `confused_with`** |
| Blobs reales no encontrados (FN) | 123 | 79 `not_detected` (64%), 39 `below_threshold` (32%), 3 `predicted_as:under_extrusion`, 2 `mislocalized` |
| Blobs reales en total | 145 | recall 0.152 = 22 / 145 |
| Tamaño mediano (lado, en el input de 640 px) | | encontrados 34.6 px, perdidos 22.3 px |

**Lo que los números establecen**
- **No es un problema de confusión entre clases**: ninguna falsa alarma cae sobre un defecto real de otra clase, y solo
  3 de 123 blobs perdidos se predijeron como otra clase (`under_extrusion`).
- **No es un problema de umbral**: solo el 32% de los blobs perdidos (39) tienen al modelo detectando la clase por debajo de
  0.25; el 64% (79) ni siquiera aparecen sobre 0.05. Bajar el umbral recuperaría como mucho un tercio del recall a cambio de
  más falsas alarmas, y aun así no llega al 90% de precisión.
- **El tamaño ayuda a explicarlo, pero no del todo**: los perdidos son más chicos que los encontrados (22.3 vs 34.6 px, ~35%
  menos). Ojo: *todos* los blobs son objetos chicos (< 35 px de mediana en el input), así que la resolución podría influir en
  toda la clase, no solo en la diferencia entre encontrados y perdidos.

**Lo observado a mano (no verificado por máquina)**: al revisar el montaje de falsas alarmas, las cajas `unannotated`
están sobre **protuberancias reales visibles en la pieza** (p. ej. una rueda dentada gris), no sobre fondo limpio; en un
caso (un vaso verde) junto a una etiqueta real de `under_extrusion`. Es decir, parecen blobs reales que el dataset de origen
no etiquetó. No se auditaron una por una las 21 cajas, así que no hay un conteo de cuántas son defectos reales.

**Interpretación (la causa más probable, no demostrada)**
1. **Etiquetado incompleto o inconsistente en el dataset de origen** (`blobs` del dataset 1, una sola fuente): hay blobs
   reales sin anotar. Un mecanismo plausible que explicaría *a la vez* el recall bajo y las "falsas alarmas": los blobs sin
   etiquetar en las imágenes de entrenamiento actúan como negativos y enseñan al modelo a ignorar la clase.
2. **Poca variedad** (1119 anotaciones, pero de una sola fuente/cámara/estilo de impresión) y **objetos chicos** como
   factores contribuyentes.

**Consecuencias para leer las métricas**
- La precisión reportada de esta clase (0.468 por caja / 0.562 por imagen) es probablemente una **cota inferior**: cada
  caja sobre un blob real sin etiquetar cuenta como falsa alarma. Como referencia aritmética (no una estimación): si las 21
  cajas `unannotated` fueran todas blobs reales, la precisión sería (22 + 21) / 47 ≈ 0.91.
- El recall (0.152) **no** sufre ese sesgo: se mide contra blobs sí etiquetados, y aun así el modelo encuentra pocos. Es la
  debilidad más sólida de la clase: **que el modelo no marque blob en una capa no es evidencia de que no lo haya.**

**Qué no se sabe (no se hizo ningún experimento)**: si limpiar/completar las etiquetas, sumar datos de otras fuentes,
entrenar a mayor resolución (`imgsz` 960/1280) o usar un modelo más grande mejoraría la clase, ni cuánto. Cada uno es un
remedio candidato; ninguno está probado.

**Decisión (sin margen de tiempo para reetiquetar un dataset de terceros ni reentrenar)**: no se toca el modelo. `blob_over_extrusion`
queda como **clase informativa**. Si se retoma: primero completar etiquetas / sumar datos de la clase (idealmente de la
cámara e impresora reales del proyecto), reentrenar, volver a correr las celdas 8c y 8d, y solo entonces evaluar quitarle el
estado informativo.

### Cómo se refleja en el sistema (clase informativa)

- **Frontend** (`frontend/src/config/defectClasses.ts`, `INFORMATIONAL_CLASSES`): en la línea de tiempo de capas cada capa
  muestra ahora sus clases detectadas como etiquetas. Las clases informativas se dibujan con borde punteado y la marca
  "· informativo" (con tooltip explicativo), y **una capa marcada solo por clases informativas se ve punteada y gris con ⓘ, no
  roja con ⚠**; si además hay una clase confiable, la capa sigue roja. Una capa con `has_defect` pero sin clases visibles
  se mantiene roja (no se degrada lo que no se puede explicar). Aparece una leyenda cuando hay alguna. Para quitarle el
  estado a una clase (p. ej. tras reentrenar), sacarla de ese mapa.
- **Backend**: `GET /print-jobs/{id}/timeline` devuelve ahora también `defect_classes` por capa (unión entre cámaras);
  `has_defect` no cambia. El backend y el worker siguen sin distinguir clases: informativa es una decisión de presentación.
- **Ninguna lógica automática depende de esta clase** (verificado en el código): solo hay dos caminos que crean alertas.
  (1) Automático: `backend/app/ws/redis_listener.py` llama a `check_jam_trend` únicamente si `under_extrusion` está entre las
  clases de la detección, y `backend/app/services/jam_detection.py` exige `under_extrusion` en 3 capas consecutivas para
  llamar a `create_alert`. (2) Manual: `POST /detections/{id}/alerts` (`api/v1/alerts.py`), que solo dispara un
  administrador a mano. Un blob no crea, no adelanta ni impide ninguna alerta.
- Lo que sí toca: `has_defect` en la base de datos sigue siendo `true` si el modelo vio un blob (es la salida cruda del
  modelo); cualquier consumidor nuevo de `has_defect` o de `defect_classes` debe decidir qué hace con las clases informativas.

## Notas

- **Re-correr con datasets nuevos**: `merge_datasets.py` regenera el split completo desde cero a
  partir de todo lo que haya en `interim/`. Como `raw/` e `interim/` viven solo en el disco
  local de Colab (no se persisten a Drive, solo el `processed.tar` final), en una sesión nueva
  **no alcanza con restaurar el `.tar` y convertir solo el dataset nuevo**: hay que volver a
  descargar y convertir los datasets anteriores también, y recién ahí correr el merge. Con todo
  en disco local eso son minutos, no horas, así que es aceptable; la celda "2b" de restauración
  sirve para *reentrenar* sin tocar los datos, no para *agregar* datos.
- **`configs/train_config.yaml`** es la única fuente de hiperparámetros - si querés más épocas,
  otro batch size, otro split, etc., editalo ahí (en Drive, o en tu repo y volvé a subirlo) en
  vez de tocar el notebook.
- El bakeoff elige ganador por el mAP50 de **stringing** específicamente (`priority_class` en
  el config), no por el mAP50 promedio - es la clase más difícil y la que más nos importa.
