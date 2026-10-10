# Etapa C2: pausa y reanudación reales con los arreglos de los hallazgos (2026-10-09)

Impresora 35 «Creality Hi-3422» (192.168.10.22). Backend desplegado el 2026-10-09 con los arreglos de los hallazgos 1 a 4 de la Etapa C (`b4e7904`, `3451c3b`,
`d425820`, `76e58f2`, `38e12ad`). `AUTO_PAUSE_MODE=warn` todo el tiempo. **PrintWatch no mandó ninguna orden a la impresora por su cuenta**: la pieza la inició Samuel desde
la pantalla de la impresora y las dos pausas y las dos reanudaciones las pulsó él en la web. Observación solo con lecturas (`GET` cada segundo a Moonraker, `SELECT`, el log
del backend y la edad del video en Redis). `capture` corría en una terminal de Samuel durante toda la prueba. Horas locales.

Pieza: **`Cubo_PLA_12m58s.gcode`** (86 capas, PLA, boquilla a 220 °C), trabajo 47, 19:18:30 a 19:36:54, `completed`. No es la `Cubo_PETG_18m27s` que se había supuesto: dura menos y
la preparación fue de unos 8 min (19:10:10 a 19:18:29), no 11.

## Sesión web

| Hora | Llamada |
|---|---|
| 18:03:07 | `POST /auth/login` → 200 (inicio de sesión de Samuel) |
| 18:36:24 | `POST /auth/refresh` → **200** (primera renovación, 33 min después del login) |
| 19:07:20 | `POST /auth/refresh` → **200** (segunda, 31 min después) |

Antes de pausar ya constaban las dos renovaciones. Durante la prueba no hubo ningún 401, 409, 502 ni 500 en el log del backend.

## Pausas y reanudaciones (medido)

| | Pausa 1 | Reanudación 1 | Pausa 2 | Reanudación 2 |
|---|---|---|---|---|
| Orden de la web («Manual … requested») | 19:22:00,306 | 19:23:07,679 | 19:25:15,966 | 19:26:33,581 |
| Orden en la bitácora (`printwatch_command`, «samuel (web)», `ok` vacío = enviada) | 19:22:00,867 | 19:23:07,815 | 19:25:16,069 | 19:26:33,779 |
| Cambio de estado en la bitácora (origen `printwatch`) | 19:22:01,438 `paused` | 19:24:13,116 `printing` | 19:25:16,904 `paused` | 19:27:37,673 `printing` |
| Del clic al cambio de estado | **1,0 s** (listener a las 19:22:01,330) | **65,4 s** | **0,84 s** | **64,1 s** |
| Respuesta de la web | 202 a las 19:22:03,874 (3,6 s) | 202 a las 19:23:10,817 (3,1 s) | 202 a las 19:25:19,071 (3,1 s) | 202 a las 19:26:36,781 (3,2 s) |
| Capa | 18 de 86 | vuelve en la 18 | 26 de 86 | vuelve en la 26 |
| Posición al pausar | X 136,1 / Y 131,5 / Z 3,7 | | X 136,1 / Y 122,3 / Z 5,1 | |

**Pausa (las dos iguales):** tras el cambio de estado la cabeza sigue moviéndose: sube a Z 50 a los ~8 s y llega al estacionamiento **X 0 / Y 260 / Z 50** a los ~20 s (19:22:22 y
19:25:36). El objetivo de la boquilla baja de 220 a 140 °C a los 12 a 14 s (19:22:14 y 19:25:30); la boquilla estaba a 164,6 °C a los 60 s en la pausa 1; la cama se mantuvo en
59,4 a 60,1 °C con objetivo 60.

**Reanudación (las dos iguales):** el objetivo de la boquilla vuelve a 220 °C al instante, llega a ≥ 215 °C a los ~20 s (19:23:28 y 19:26:56), la cabeza baja de Z 50 a Z 6,2 y va a
X −18,5 / Y 130 (a **0,5 mm del límite −19**, igual que en la Etapa C, sin error), y el estado vuelve a `printing` a los ~65 s. Rango recorrido en la reanudación 2: X −18,5 a 137,4,
Y 130 a 260 (límites X −19..285, Y −7..273). **Ningún error de Klipper ni `resume_err`** en toda la prueba. La orden de reanudar no figura como fallida (sin `ReadTimeout`).

## Incidentes y bitácora

- Incidentes 3 y 7 (`would_pause`, modo `warn`, clase `spaghetti`): abiertos a las 19:20:10 y 19:24:58 por la detección; las pausas de Samuel los marcaron `paused` (19:22:01 y 19:25:16) y las
  reanudaciones los cerraron como `resumed` por «samuel (web)» (19:24:13 y 19:27:37). `pause_sent_at` vacío: PrintWatch no mandó ninguna pausa (modo `warn`).
- Cadena de la bitácora de la impresora 35: **íntegra, 340 eventos**. Las órdenes y los cambios de estado aparecen en ese orden y atribuidos a `printwatch` (el hallazgo 4 ya no se da).

## Capturas y video (con `capture` corriendo)

- **86 capas y 86 capturas, ninguna sin captura.** Retraso de la captura respecto a la capa: mínimo 0,4 s, medio 0,7 s, máximo 1,8 s. Tabla completa en
  [etapa_c2/capturas_trabajo_47.txt](etapa_c2/capturas_trabajo_47.txt) (consultas en [c2_capturas.sql](c2_capturas.sql)).
- **Huecos:** los de las pausas: capa 18 → 19, **140,4 s**, y capa 26 → 27, **149,9 s**; otros dos de 13,7 y 13,8 s (capa 2 y capa 83) sin relación con las pausas.
  **0 capturas durante cada pausa**, como se esperaba (se capturan por capa).
- **Primera captura tras reanudar:** capa 19 a las 19:24:15, **2,3 s** después de volver a `printing`; capa 27 a las 19:27:44, **6,6 s** después.
- **Video en vivo (Redis):** edad máxima **0,76 s** en 1 145 muestras (desde las 19:18:30), ninguna mayor de 2 s: no se cortó en la pausa ni en la reanudación.
- 1 068 muestras de telemetría en la base.

## Detecciones (modo `warn`, no actuó nada)

20 detecciones de `spaghetti` (confianza 0,258 a 0,570) y 1 de `under_extrusion` (0,334) en 86 capas; el modelo avisó 3 veces de una racha de 3 capas seguidas (19:20:10 capa 6, 19:21:36 capa 16,
19:24:58 capa 24). **Se miró la foto de la capa 24 (la de mayor confianza, 0,570): no muestra la pieza en el encuadre**; la cámara ve la cama de lado con el cabezal a la izquierda y la pieza no se
ve, así que esa detección no puede corresponder a un spaghetti real. De las otras no se miró ninguna. No se declara la causa más allá de eso (la cámara es la genérica, no está en la posición de la
calibración y no ve la pieza); con `AUTO_PAUSE_MODE=on` estas detecciones habrían pausado la impresión.

## Qué se comprobó de los arreglos (con la impresora real)

| Hallazgo | Resultado |
|---|---|
| 1. Respuesta «aceptada» sin esperar a la impresora | **Comprobado**: 202 a los ~3 s en las 4 órdenes (no 502); la orden queda como enviada y no como fallida; la reanudación real tardó ~65 s |
| 4. Atribución de la pausa a `printwatch` | **Comprobado**: las dos pausas y las dos reanudaciones, `printwatch`, con la orden antes del cambio de estado |
| 3. Sesión | **Comprobado**: dos renovaciones con 200 antes de la prueba y ningún 401 durante ella |
| 2. Guarda de reanudación en curso | **No probado**: nadie pulsó un segundo clic mientras reanudaba |
| Pausa con lectura previa del estado (`38e12ad`) | Camino feliz usado en las dos pausas; el camino de impresora inalcanzable no se probó con la real |

**No medido:** lo que la web mostró en pantalla («Pausando…», «Reanudando… N s»); no se observó el navegador de Samuel.

## Qué sigue

1. Decidir `AUTO_PAUSE_MODE` a la vista de las detecciones falsas con esta cámara (y la pausa automática inducida, que necesita «autorizo la C»).
2. Cancelación real, solo con «autorizo cancelar».
3. Reposicionar la cámara para que vea la pieza y recalibrar con la C922 (y revisar el umbral de `spaghetti` antes de pasar a `on`).
4. Pendientes de la cámara: aviso de «captura detenida» en la web y un script que arranque `capture` comprobando antes la cámara.

## Revisión de detecciones (2026-10-09, 19:45 a 19:55)

Solo lectura: nada se mandó a la impresora, no se cambió ninguna configuración (ni umbrales ni la región de interés de la cámara) y no se tocó el código.
Evidencia en [etapa_c2/revision_detecciones/](etapa_c2/revision_detecciones/): `en_vivo.jpg` y cuatro hojas con las 21 fotos y el recuadro de cada detección dibujado.

### 1. Foto en vivo de la cámara 36 (19:46, `capture` corriendo, impresora en `complete`)

`/snapshot` 200, 135 907 bytes, edad 0,0 s. **La cama se ve con claridad**: nítida y bien iluminada, vista muy de lado (rasante), con su borde y el rótulo «BUILD VOLUME 260×260×300 mm³», el cabezal
arriba y el escritorio a la derecha. **El cubo terminado no se ve**: en el centro de la cama, ampliado, solo hay una marca pequeña (un resto o una mancha) y nada con forma de cubo; lo más probable es que Samuel
lo retiró, pero no se puede afirmar con la foto (podría ser también una pieza negra sobre la placa negra, que se vería como una sombra mayor que esa marca).

### 2. Las 21 detecciones del trabajo 47 (20 `spaghetti` y 1 `under_extrusion`)

**Ninguna es real.** En las 21 fotos el recuadro cae en el mismo sitio, el borde derecho de la imagen (x 0,81 a 1,00, y 0,30 a 0,57), y encierra siempre el mismo objeto: una **pieza blanca impresa y articulada que está
sobre el escritorio, junto a la impresora** (y un trapo rojo debajo). No es la pieza que se imprime, ni filamento suelto. En ninguna de las 21 fotos se distingue la pieza sobre la cama (no sé si por el ángulo, muy rasante, o por su tamaño y color), así que tampoco hay un
defecto real visible que estas detecciones hubieran podido acertar por casualidad.

| Capa | Clase | Confianza | ¿Real? | Qué encierra el recuadro |
|---|---|---|---|---|
| 1 | under_extrusion | 0,334 | No | la pieza blanca del escritorio |
| 4 | spaghetti | 0,282 | No | ídem |
| 5 | spaghetti | 0,344 | No | ídem |
| 6 | spaghetti | 0,278 | No | ídem (aquí saltó el aviso de racha de las 19:20:10) |
| 7 | spaghetti | 0,501 | No | ídem |
| 8 | spaghetti | 0,415 | No | ídem |
| 9 | spaghetti | 0,274 | No | ídem |
| 10 | spaghetti | 0,370 | No | ídem |
| 11 | spaghetti | 0,325 | No | ídem |
| 12 | spaghetti | 0,258 | No | ídem |
| 14 | spaghetti | 0,310 | No | ídem |
| 15 | spaghetti | 0,418 | No | ídem |
| 16 | spaghetti | 0,493 | No | ídem (aviso de las 19:21:36) |
| 17 | spaghetti | 0,438 | No | ídem |
| 18 | spaghetti | 0,551 | No | ídem |
| 19 | spaghetti | 0,368 | No | ídem |
| 20 | spaghetti | 0,554 | No | ídem |
| 22 | spaghetti | 0,379 | No | ídem |
| 23 | spaghetti | 0,316 | No | ídem |
| 24 | spaghetti | 0,570 | No | ídem (aviso de las 19:24:58) |
| 34 | spaghetti | 0,319 | No | ídem |

Nota: la foto de la capa 1 tiene otro encuadre (cambió justo al empezar); desde la capa 4 es el mismo en todas.

### 3. Umbrales

**Los actuales** (leídos del código y de la configuración; no se cambió ninguno):
- **Modelo:** confianza mínima **0,25 para todas las clases** (`inference/config.py`, variable `CONFIDENCE_THRESHOLD`; calibrada en el split de prueba de 841 imágenes; los umbrales por clase se descartaron a propósito). Todo lo que
  llega a 0,25 se guarda como detección.
- **Racha de `spaghetti` (aviso `would_pause` / pausa automática):** 3 capas seguidas con `spaghetti` entre sus clases, **sin umbral de confianza propio**: usa lo que guarda el modelo, o sea ≥ 0,25.
- **Incidente por una sola detección:** `spaghetti` o `layer_shift` con confianza **≥ 0,50** (`incident_min_confidence`). `stringing` y `blob_over_extrusion` nunca abren incidente.

**Con qué umbral de `spaghetti` habría quedado en cero el aviso de racha en este trabajo** (calculado sobre las 86 capas; las capas sin detección cuentan como 0):

| Umbral de spaghetti | Capas que lo alcanzan | Avisos de racha de 3 capas |
|---|---|---|
| 0,25 (el actual) | 20 | **3** (capas 6, 16 y 24) |
| 0,30 | 16 | 2 |
| 0,35 | 11 | 1 |
| 0,40 | 8 | 1 |
| 0,43 | 6 | 1 |
| **0,44** | 5 | **0** |
| 0,50 | 4 | 0 |
| 0,55 | 3 | 0 |
| 0,58 | 0 | 0 |

El mayor umbral que aún deja una racha es **0,438** (capas 16, 17 y 18: 0,493, 0,438 y 0,551): **cualquier umbral por encima de 0,438 (por ejemplo 0,44) deja el aviso en cero.** Con 0,44 dejarían de contar 15 de las
20 detecciones (las de menos de 0,44) y quedarían 5. **Detecciones reales que se habrían perdido: 0**, porque en este trabajo no hubo ninguna real (las 21 son falsas).

**Por qué no basta con esa cifra:**
1. **No hay ningún caso real de `spaghetti` con el que medir lo que se pierde.** Los trabajos anteriores con capturas (34, 35 y 44) no tienen ninguna detección de `spaghetti` (0 de 177 capas): este es el único trabajo con ellas, y son todas falsas.
   Subir el umbral a 0,44 no está validado con spaghetti real y la calibración del modelo (0,25) se hizo con otro criterio.
2. **0,44 está muy justo**: el límite es 0,438; con otro fondo o con la cámara en otro sitio el mismo objeto podría dar 0,5 o más (en este trabajo ya dio 0,570).
3. **Incluso con 0,44 quedan 4 capas con 0,50 o más (7, 18, 20 y 24)** que abrirían incidentes por una sola detección (no pausan, pero ensucian la lista); para evitarlo habría que pasar de 0,57 (0,58), con lo que el modelo
   no detectaría nada de spaghetti con esta imagen.
4. **La causa no es el umbral sino el encuadre**: la zona del recuadro es siempre la misma y es un objeto fijo del escritorio. La cámara tiene una región de interés (`cameras.roi`, que recorta el fotograma antes de la inferencia), hoy sin
   definir (fotograma completo) para la cámara 36; acotarla a la cama (después de reposicionar la cámara para que vea la pieza) quitaría estas detecciones sin tocar el modelo ni los umbrales. No se aplicó.

**Conclusión (sin cambiar nada):** con esta cámara y este encuadre, `AUTO_PAUSE_MODE=on` habría pausado una pieza que iba bien (3 veces en 86 capas). Antes de pasar a `on`: reposicionar la cámara, definir la región de
interés de la cama y volver a medir con una pieza real (y, a ser posible, con un spaghetti real); subir el umbral queda como último recurso.

## Propuesta de región de interés para la cámara 36 (2026-10-09, 20:20 a 20:40)

Solo lectura y propuesta: **no se aplicó nada**, no se escribió en la base de datos y no se tocó la impresora. La foto de este apartado se tomó en vivo a las 20:24 (`/snapshot`, 150 302 bytes, edad 0,7 s) y está en
[etapa_c2/revision_detecciones/en_vivo_2.jpg](etapa_c2/revision_detecciones/en_vivo_2.jpg); con los rectángulos dibujados, en [en_vivo_2_roi.jpg](etapa_c2/revision_detecciones/en_vivo_2_roi.jpg).

### 1. Qué se ve ahora (la cámara cambió de sitio respecto a las fotos del trabajo 47)

- **La cama casi completa, pero no entera.** Se ve el borde trasero, el lado izquierdo y el borde delantero. **La esquina delantera derecha queda fuera del encuadre** (el borde derecho de la imagen la corta) y
  la delantera izquierda toca el borde inferior.
- **Sobre la cama hay un solo objeto: un cubo blanco** (aprox. x 658 a 750, y 360 a 440), en la parte trasera central, con su reflejo en la placa brillante. Es la pieza.
- **Fijo alrededor, lo que podría confundirse:** un cable de red azul que baja por detrás y recorre el lado derecho de la cama sobre el escritorio (x 920 a 1280, y 290 a 420); un cable negro grueso a la izquierda (x 50 a 230, y 300 a 360); un cable
  blanco fino detrás del cabezal (x 830 a 870, y 140 a 200); una caja de cartón verde abajo a la izquierda (x 0 a 100, y 505 a 700); un trapo rojo en el borde derecho (x 1240 a 1280, y 425 a 460); la superficie beige
  del escritorio a la derecha; y partes de la propia impresora (el bloque trasero, x 250 a 650, y 295 a 350, el poste y el cabezal). **La pieza blanca articulada del escritorio que dio las 21 falsas detecciones ya no sale en la imagen.**

### 2. El modelo de producción sobre esa foto (umbral 0,25, solo lectura)

Se pasó la foto por el mismo modelo y el mismo código del worker (`best_fp32.onnx`, `inference/model.py`) ejecutándolo dentro de su contenedor, sin guardar nada en la base de datos ni en Redis:

| Caso | Detecciones |
|---|---|
| Foto completa, umbral 0,25 (el de producción) | **ninguna** |
| Foto recortada a la región propuesta, umbral 0,25 | **ninguna** |
| Solo contexto: foto completa y recortada con umbral 0,10 | **ninguna** |

El cubo blanco sobre la cama tampoco se marca. **Con este encuadre las falsas detecciones ya no aparecen ni siquiera sin región de interés**; la región sería una protección adicional, no el arreglo. Limitación: es una sola foto fija con la impresora
en reposo; con una impresión en marcha (cabezal en movimiento, cables que se mueven) puede haber otras cosas.

### 3. La cama medida en la foto (fotograma de 1280×720)

| | x | y | ancho | alto | Relación ancho/alto |
|---|---|---|---|---|---|
| Rectángulo que cubre solo la cama, en píxeles | 110 | 318 | 1170 | 402 | 2,91 |
| Ídem, en proporciones de 0 a 1 | 0,086 | 0,442 | 0,914 | 0,558 | |
| **Región propuesta (margen de ~10 px a la izquierda y ~20 px arriba), en píxeles** | **100** | **300** | **1180** | **420** | 2,81 |
| **Región propuesta, en proporciones de 0 a 1** | **0,078** | **0,417** | **0,922** | **0,583** | |

La cama se midió sobre una cuadrícula de 100 px: esquina trasera izquierda hacia (115, 372), trasera derecha hacia (800, 322), delantera izquierda hacia (430, 705); la delantera derecha cae fuera de la imagen, por eso el rectángulo
llega hasta el borde derecho (1279). La placa es un trapecio, así que el rectángulo incluye algo de lo que la rodea: el bloque trasero de la impresora, un trozo de cable negro a la izquierda, el cable azul, el trapo rojo y el escritorio a la derecha.
Deja fuera la caja verde, el cabezal, el poste y el cable blanco.

**Dos reservas de la propuesta:**
1. **Deformación.** El worker redimensiona el recorte a 640×640 estirándolo (sin conservar proporciones). El fotograma completo se deforma ya 1,78 veces (1280×720); el recorte propuesto, 2,81 veces. No se sabe cómo afecta eso al modelo, y no hay un
   defecto real en esta foto para medir si deja de detectarlo.
2. **Vale solo para esta posición de la cámara.** Si se mueve (por ejemplo para encuadrar la esquina delantera derecha), hay que volver a medir. Es independiente de la calibración de la cama.

### 4. Cómo se aplicaría y cómo se deshace (no se ejecutó)

La región vive en `cameras.roi` (JSON con `x`, `y`, `w`, `h` en píxeles del fotograma completo); hoy la cámara 36 la tiene **vacía** (`select id, name, roi from cameras where id = 36;` → vacío). El worker la lee en cada mensaje, así que **surte efecto en la
siguiente capa analizada, sin reiniciar nada**. Los recuadros se vuelven a convertir al fotograma completo (`inference/main.py`, `backend/app/api/v1/incidents.py`, `backend/app/services/defect_map.py` ya lo hacen), y las detecciones ya
guardadas conservan la región con la que se hicieron (`raw_output.frame.roi`). **No requiere reconstruir ni reiniciar nada, ni el backend ni el worker.**

- **Aplicar:** [etapa_c2/roi_camara_36_aplicar.sql](etapa_c2/roi_camara_36_aplicar.sql) (solo actúa si `roi` está vacío):
  `update cameras set roi = '{"x": 100, "y": 300, "w": 1180, "h": 420}'::jsonb where id = 36 and roi is null;`
  Comando (PowerShell, desde la raíz del repo):
  `Get-Content docs\laboratorio\etapa_c2\roi_camara_36_aplicar.sql | wsl docker exec -i infra-postgres-1 sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f -'`
- **Deshacer:** [etapa_c2/roi_camara_36_deshacer.sql](etapa_c2/roi_camara_36_deshacer.sql): `update cameras set roi = null where id = 36;` con el mismo comando cambiando el archivo.
- **Alternativa por la API** (solo administradores): `PATCH /api/v1/cameras/36` con el cuerpo `{"roi": {"x": 100, "y": 300, "w": 1180, "h": 420}}`; para deshacer, `{"roi": null}`. La API no valida las claves del JSON: una clave que falte haría fallar el análisis de cada capa, por eso es
  preferible la consulta con los valores ya escritos.
- **Comprobar después:** esperar una capa y mirar `select raw_output->'frame'->'roi' from detections order by id desc limit 1;` (debe mostrar la región) y que la edad del video en la web siga bien (la región no afecta al video).

**Recomendación:** de momento no aplicarla: con el encuadre actual el modelo no detecta nada ni con 0,10, y la región añade una deformación que no se ha medido. Si se aplica, hacerlo con `AUTO_PAUSE_MODE=warn` y comparar con una impresión real; antes, encuadrar también la esquina
delantera derecha de la cama.

## Prueba con un enredo de filamento sobre la cama (2026-10-09, 20:34)

Solo lectura: nada se aplicó, no se escribió en la base de datos ni en Redis y no se tocó la impresora (seguía en `complete`). Foto en vivo de la cámara 36 a las 20:34 (`/snapshot`, 158 836 bytes, edad 0,3 s):
[etapa_c2/revision_detecciones/en_vivo_3_enredo.jpg](etapa_c2/revision_detecciones/en_vivo_3_enredo.jpg); con las cajas dibujadas,
[en_vivo_3_enredo_cajas.jpg](etapa_c2/revision_detecciones/en_vivo_3_enredo_cajas.jpg). La cámara cambió otra vez de encuadre: ahora ve **la cama entera, de frente**, con el cubo blanco en la parte trasera y, a su izquierda, un pequeño enredo
de filamento blanco (más un hilo fino que sube por encima de la esquina izquierda del cubo).

### 1. El modelo de producción (mismo código y pesos del worker, ejecutado en su contenedor)

| Caso | Resultado |
|---|---|
| Foto completa, umbral **0,25** (producción) | **ninguna detección** |
| Foto completa, umbral 0,10 (solo contexto) | **ninguna detección** |

**El modelo no ve el enredo en las condiciones de producción**: no hay `spaghetti`, ni ninguna otra clase, ni siquiera con 0,10.

**Contexto adicional (no es lo que hace producción; solo para saber a partir de qué tamaño se ve):** pasando al modelo recortes de la misma foto,

| Recorte que se le da al modelo | Umbral 0,25 y 0,10 | Dónde cae el recuadro |
|---|---|---|
| 240×240 alrededor del enredo (x 440, y 250) | **`spaghetti` 0,422** | x 523 a 572, y 346 a 389 (px del fotograma completo) = el enredo |
| 400×225 alrededor del cubo (x 380, y 240) | **`spaghetti` 0,354** | x 522 a 574, y 353 a 393: el enredo |
| Región de la cama completa (x 60, y 290, 1200×350) | ninguna | |

El recuadro del modelo coincide con el enredo medido a mano (ver abajo): cuando el modelo lo ve, lo encierra bien.

### 2. Tamaño del enredo (fotograma de 1280×720)

Medido sobre una ampliación de 6× con cuadrícula de 10 px (incertidumbre de unos ±3 px) y confirmado por el recuadro del modelo:

| Medida | Valor |
|---|---|
| Enredo (masa de filamento a la izquierda del cubo) | x 523 a 572, y 346 a 389: **48 × 43 px**, 2 076 px² |
| Fracción de la imagen | ancho **3,8 %**, alto **6,0 %**, **área 0,225 %** |
| Fracción del rectángulo de la cama (x 75 a 1240, y 297 a 640) | **0,52 %** del área |
| Respecto al cubo (73 × 80 px, 5 840 px², 0,63 % de la imagen) | el enredo mide dos tercios de su ancho y algo más de la mitad de su alto: **el 36 % de su área** |
| Hilo fino que sube sobre el cubo | unos 4 × 24 px |
| Lo que ve el modelo con la foto completa (entrada de 640×640) | 24 × 38 px |
| Lo que ve el modelo con el recorte de 240×240 | 129 × 114 px (el enredo ocupa el 3,6 % de lo que ve) |
| Con el recorte de 400×225 | 77 × 122 px (2,3 % de lo que ve) |

### 3. Qué dice de lo pequeño que puede ser un fallo y aún verse

- **Con la cámara a esta distancia y el fotograma completo, un enredo de 48 × 43 px (0,23 % de la imagen) no se detecta.** Se detecta cuando ocupa más imagen en lo que ve el modelo: con el 2,3 % (recorte 400×225) da 0,354 y con el 3,6 %
  (recorte 240×240) da 0,422; con el 0,49 % (región de la cama de 1200×350) sigue sin verse. Para este enredo el límite de visibilidad cae **entre el 0,5 % y el 2,3 % de la imagen que recibe el modelo**.
- Es **un solo ejemplo**: filamento blanco sobre la placa oscura (mucho contraste) y de un tamaño concreto. No dice cuál es el mínimo general ni cómo responde el modelo a un spaghetti real, que suele ser mucho mayor.
- **Consecuencia para el sistema:** con la cámara a esta distancia y el modelo recibiendo el fotograma entero, un fallo pequeño como este pasaría desapercibido (y el aviso de racha pide además 3 capas seguidas). Acercar la cámara, recortar la región de interés a la cama
  o analizar la cama por mosaicos haría que ocupe más imagen; la región de la cama completa (la propuesta anterior) **no basta** para este tamaño, y un recorte mucho más cerrado no es posible porque un fallo puede estar en cualquier punto de la cama. No se cambió nada.
- **La propuesta de región de interés de la sección anterior queda desfasada para este encuadre** (la cama ahora ocupa aprox. x 75 a 1240, y 297 a 640): habría que volver a medirla cuando se fije la posición de la cámara.
