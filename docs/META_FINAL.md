# Meta final: detectar un fallo inminente e intervenir con éxito

**Meta del proyecto:** que PrintWatch detecte un fallo inminente en la impresora e intervenga con éxito, mostrando
en la web el reporte completo y todos los parámetros necesarios de la impresora.

**Estado de este documento:** Paso 1 (propuesta). Se escribió leyendo el código real y los datos medidos; **no se
cambió ningún código** ni se mandó nada a una impresora. Los números marcados como *propuesta* son una sugerencia para
que Samuel (y el profesor) los acepten o cambien; los marcados como *medido* salen de las pruebas del laboratorio
(`docs/laboratorio/HALLAZGOS_PARA_INFORME.md`). Espera el ok de Samuel antes del Paso 2 (la pantalla de «Incidente»).

Convención para distinguir lo comprobado de lo supuesto:

- **Real**: se probó con la impresora Creality Hi real.
- **Simulada**: se probó solo con la impresora simulada (`mock_moonraker.py`) o con pruebas automáticas.
- **Supuesto**: está escrito en el código o en un documento, pero nadie lo ha medido.
- **No existe**: falta.

---

## a) Definición de «éxito» medible

### a.1 Qué cuenta como fallo inminente

Un **fallo inminente** es un estado de la impresión en el que, si nadie interviene, el daño crece con el tiempo
(filamento y horas perdidas, boquilla o cama dañadas) y el modelo lo ve con evidencia persistente, no en una sola foto.
Se separa por clase de defecto, según lo que el propio modelo mide (precisión y recall a nivel imagen con umbral 0,25,
841 imágenes de prueba de Roboflow; **no hay ninguna medida con la cámara y la impresora reales**):

| Clase | Precisión / recall del modelo | ¿Inminente? | Por qué |
|---|---|---|---|
| `spaghetti` | 0,963 / 0,975 | **Sí** | Filamento suelto o enredado: la pieza ya falló y la boquilla sigue extruyendo; cada minuto es filamento perdido y riesgo de enredo en el cabezal. |
| `layer_shift` | 1,0 / 1,0 | **Sí** | La pieza queda desalineada desde esa capa; todo lo que se imprima encima es desperdicio. |
| `warping` | 0,988 / 0,988 | Solo si persiste y crece | Una esquina levantada puede ser tolerable; si se despega, la boquilla la golpea. |
| `under_extrusion` | 0,919 / 0,685 | Solo con 3 capas (hoy: alerta crítica) | Hilo flojo o atasco parcial; el recall es bajo, así que no es una señal confiable por sí sola. |
| `stringing` | 0,977 / 0,959 | **No** | Cosmético. |
| `blob_over_extrusion` | 0,562 / 0,529 | **No** | Precisión demasiado baja; clase informativa (ya así en la web). |

Además de la imagen, hay **fallos que la impresora ya detecta ella misma** (error de Klipper, sensor de filamento
agotado, temperatura fuera de control): PrintWatch no los provoca ni los intercepta; los **registra** y los muestra
(`state_changed` a `error`, `filament_sensor_changed`). No cuentan como éxito ni como fallo de PrintWatch.

### a.2 Tiempo máximo entre la aparición del defecto y la pausa

Presupuesto de tiempo del camino actual (de la primera foto en la que se ve el defecto hasta que Klipper está en
`paused`):

| Tramo | Valor | Origen |
|---|---|---|
| Aviso de cambio de capa (Moonraker → PrintWatch) | ≤ 0,25 s | *medido* (un mensaje de estado cada 0,251 s) |
| Foto de la capa | 0,29 a 1,77 s (media 0,52) | *medido* (trabajo 44) |
| Inferencia del modelo + guardado | 0,49 a 2,40 s (media 0,87) | *medido* (trabajo 44) |
| Aviso interno al chequeo de racha (Redis pub/sub + consulta) | no medido, milisegundos | *supuesto* |
| **Persistencia: 3 capas con el defecto** | **3 × tiempo de capa**: 6 s (trabajo 44), ~46 s en promedio (trabajo 43), hasta **24 min** en una capa (trabajo 43) | *medido*; este tramo domina todo lo demás |
| Cuenta regresiva (gracia) | 15 s fijos | código (`_GRACE_PERIOD_SECONDS`) |
| Envío del `pause` y estado `paused` confirmado | tiempo de espera de 10 s; **sin medir con la impresora** | *supuesto* |

De punta a punta de la parte automática (foto → resultado): **p90 2,5 s, máximo 3,2 s** (*medido*). Lo que no está
acotado es la persistencia por capas: con capas lentas, «3 capas» pueden ser decenas de minutos.

**Propuesta de objetivo:** desde la primera foto con el defecto hasta el estado `paused` confirmado por la impresora,
**P90 ≤ 3 min** (incluidos los 15 s de gracia y el envío), y **nunca más de 3 capas ni 3 minutos, lo que ocurra
primero**. Cumplirlo con capas largas exige tomar fotos adicionales entre capas (hoy solo hay una por cambio de capa).

### a.3 Falsos positivos tolerables

Un falso positivo en modo `on` pausa una impresión sana (hay que ir, mirar, reanudar) y obliga a pasar por la
secuencia de reanudación de Creality, que **ya falló una vez** (incidente del 25-09). Con persistencia de N capas y
errores independientes de probabilidad *p* por foto, la probabilidad de una pausa falsa en una impresión de L capas es
aproximadamente *L × pᴺ*. Para que sea ≤ 1 % en una impresión de 500 capas hace falta:

- N = 3 → *p* ≤ **2,7 %** por foto sana (spaghetti).
- N = 2 → *p* ≤ **0,45 %** por foto sana (layer_shift).

(Es una cota optimista: los errores de capas seguidas no son independientes, porque una pieza o un fondo que confunde
al modelo lo confunde en todas las capas.) **Propuesta de objetivo, a medir con la cámara y la pieza reales:**

- En modo `warn`: **≤ 1 «habría pausado» falso por cada 20 horas de impresión sana**, contado con
  `auto_pause.would_pause` y etiquetado a mano.
- Antes de pasar a `on`: **0 pausas falsas en 10 impresiones sanas seguidas** (de al menos 30 min cada una).
- La tasa por foto *p* (cuántas fotos sanas el modelo marca como `spaghetti`) **se mide con las mismas impresiones** y
  debe quedar por debajo de las cotas de arriba.

### a.4 Fallos no detectados tolerables

- **Propuesta:** en las pruebas con fallos reales o inducidos, **la pausa debe ocurrir antes de que el fallo desperdicie
  más de ~10 minutos de impresión** y con **recall ≥ 80 %** (con pocos fallos, se informa «k de n», no un porcentaje:
  con 10 fallos no se puede demostrar el 90 %).
- Con el recall de `under_extrusion` en 0,685 no se promete pausarla; solo avisarla.

### a.5 Qué debe quedar registrado de cada incidente

Para cada incidente (una racha que cierra la regla, en `warn` o en `on`, o una pausa real por cualquier origen):

1. **Evidencia:** trabajo, impresora, cámara; las capas de la racha con su foto, sus cajas, clase y confianza; hora de
   la primera foto con el defecto y hora del resultado del modelo.
2. **Decisión del sistema:** modo (`on`/`warn`), qué regla se cumplió (parámetros vigentes), hora del aviso, hora de
   envío del `pause`, hora en que la impresora quedó en `paused`.
3. **Estado de la impresora en ese instante:** temperaturas y objetivos, velocidad real y factor de velocidad, flujo,
   ventilador, posición, sensores de filamento, progreso, capa, tiempo impreso y restante.
4. **Respuesta humana:** quién y cuándo abortó la cuenta, reanudó, canceló o ignoró; y si el usuario lo etiquetó como
   **acierto o falso positivo** (hoy no existe).
5. **Desenlace:** reanudó y terminó, canceló, o la impresora terminó en `error`.
6. **Integridad:** todo lo anterior que sea un evento va en la bitácora encadenada por hashes (ya verificable).

### a.6 Qué cuenta como «intervenir con éxito»

Éxito de una intervención = **(1)** la impresora confirma `paused` dentro de 20 s del envío; **(2)** el incidente queda
con todo el registro de a.5; **(3)** el usuario puede decidir desde la web (reanudar o cancelar) y la orden se ejecuta
sin que Klipper termine en `error`. Como la reanudación ya falló una vez en la Hi, **se mide aparte**: mientras no se
valide (Etapa C, con autorización), una intervención exitosa termina en «pausada y con la decisión en manos del
usuario», no en «reanudó sola».

### a.7 Cómo se valida (fases)

1. **Observación en `warn`** con la cámara final (C922) bien colocada: contar `would_pause` y etiquetarlos (acierto o
   falso positivo). Sin riesgo para la impresora.
2. **Medir *p*** por foto y el tiempo real por capa; ajustar la regla (sección c).
3. **Fallo inducido y desechable** (Etapa C, solo con «autorizo la C»): pieza corta que se despega a propósito, con la
   mano junto al interruptor; medir a.2 de verdad, incluida la pausa real y la decisión desde la web.
4. **Activar `on`** solo para la clase y el umbral que cumplieron a.3.

---

## b) Auditoría de brechas (leyendo el código real)

### b.1 Lo que existe

| Pieza | Qué hace | Evidencia | Estado |
|---|---|---|---|
| Detección de capa (`listener._handle_layer_change`) | Con `virtual_sdcard.layer` crea la capa y publica `layer_ready` | trabajo 44: 32 de 32 capas, 1 por cambio de capa | **Real** |
| Foto por capa (`capture`) | Guarda el cuadro y lo encola para el modelo | 32 de 32 fotos, ~150 KB | **Real** (con cámara genérica, sin la pieza a la vista) |
| Modelo (`inference/model.py`, ONNX FP32, un hilo, umbral global 0,25, NMS sin clase) | Cajas, clase y confianza | corre y responde en 0,5 a 2,4 s | **Real** el mecanismo; **Supuesto** el rendimiento (métricas solo de Roboflow) |
| Racha (`streak_detection.check_consecutive_streak`) | 3 capas seguidas con la clase | pruebas automáticas y simulada | **Simulada** |
| Auto-pausa (`auto_pause.py`) | Aviso, cuenta de 15 s, `pause`; modos `on`/`warn`/`off` | pruebas con la simulada, que sí cambia de estado; demostración | **Simulada** |
| `would_pause` en `warn` | Evento en la bitácora con capa, confianza, racha | prueba automática; 0 eventos en el trabajo 44 (0 defectos) | **Simulada** |
| Envío de órdenes (`client.send_print_action`) | `POST /printer/print/<acción>` y registro en memoria | pausa manual del 25-09 funcionó | **Real** (pausa manual) |
| Guarda de reanudación (`print_guard`) | Una a la vez, 20 s, solo si la impresora dice `paused` | 5 pruebas con la simulada | **Simulada** |
| Bitácora (`printer_events`) | Origen de cada cambio (gcode_file, console, external, printer, printwatch), cadena de hashes | cadena íntegra en cada verificación (75 eventos al cerrar el trabajo 44, 82 después) | **Real** |
| Telemetría | Una muestra por segundo con todo lo de a.5.3; `layers.telemetry` al cambiar de capa | 206 muestras en 214 s, sin huecos | **Real** |
| Reporte PDF del trabajo | Resumen, gráficas, bitácora, integridad | PDF de los trabajos 43 y 44 | **Real** |
| Banner web de auto-pausa (`AutoPauseOverlay`) | Cuenta, «Abortar», «Reanudar» tras pausa automática | solo con la demostración | **Simulada** |
| Botones Pausar/Reanudar (`PrintControls`) | Piden confirmación y llaman a la API | pausa manual del 25-09 | **Real** (pausar); reanudar **falló** esa vez |

### b.2 Lo que nunca se ha probado con la impresora real

1. **La auto-pausa de punta a punta**: nunca hubo una capa con *spaghetti* real en una impresión seguida por
   PrintWatch; el `pause` automático (`auto_pause._execute`) nunca se ejecutó contra la Hi.
2. **La reanudación**: la única vez (25-09) terminó en `Move out of range` (X = 292,424 contra un límite de 285). La
   guarda nueva nunca se probó contra la Hi.
3. **El modelo con imágenes de la cámara final (C922)** y con la pieza a la vista: las 32 fotos del trabajo 44 son de
   una cámara genérica provisional que no mostraba la pieza.
4. **El `warn` con datos reales**: dio 0 eventos porque no hubo defectos.
5. **Atribución de cambios de factor de velocidad** (pantalla y Fluidd): no se hicieron.

### b.3 Brechas (qué falta), de mayor a menor importancia para la meta

| # | Brecha | Qué pasa hoy | Evidencia en el código |
|---|---|---|---|
| G1 | **No hay «incidente» como entidad.** | Lo que ocurre queda repartido: un banner efímero por WebSocket, un evento `auto_pause.would_pause` (solo en `warn`), un `printwatch_command` si se envió la pausa, detecciones sueltas. No hay un registro único consultable ni una pantalla. | `auto_pause.py`, `listener._log_sent_commands` |
| G2 | **La cuenta regresiva y el «Abortar» no se registran.** | `auto_pause.pending` y `auto_pause.aborted` solo se difunden por WebSocket; si nadie tiene la web abierta, no queda rastro de que hubo una cuenta ni de quién la abortó. | `auto_pause.check_spaghetti_streak`, `abort`, `print_jobs.abort_auto_pause` |
| G3 | **Cancelar no existe.** | `send_print_action` admite `cancel` y el listener sabe atribuir `cancelled`, pero **no hay endpoint, guarda ni botón**. | `printers.py` solo tiene `/pause` y `/resume`; `grep cancel` en la web: nada |
| G4 | **«Ejecutada» no es «pausada».** | `auto_pause.executed` se emite cuando el HTTP del `pause` responde bien, no cuando Klipper pasa a `paused`; no hay confirmación ni reintento ni alarma si no pasa. | `auto_pause._execute` |
| G5 | **Solo `spaghetti` puede pausar.** | `layer_shift` (recall 1,0) y `warping` no tienen regla; `under_extrusion` solo genera alerta. | `redis_listener`: solo `"spaghetti" in defect_classes` |
| G6 | **Tiempo no acotado.** | La persistencia se cuenta en capas y las fotos solo ocurren al cambiar de capa; una capa lenta (24 min medidos) retrasa todo. | `_handle_layer_change`, `check_consecutive_streak` |
| G7 | **El camino no es durable de punta a punta.** | Foto → modelo va por una cola durable (Redis Stream con grupo de consumidores), pero un mensaje que falla queda pendiente y **nadie lo reclama** (el worker lee solo mensajes nuevos, `>`). Modelo → backend va por **Redis pub/sub, sin persistencia**: si el backend se reinicia en ese momento, esa detección no llega a la auto-pausa, y al arrancar no hay un barrido de «detecciones recientes sin evaluar». La cuenta pendiente (`_pending`) y el registro de órdenes (`command_log`, 10 min) están en memoria. | `inference/main.py` (`xreadgroup ... ">"`), `redis_listener`, `main.lifespan`, `AutoPauseManager._pending`, `command_log` |
| G8 | **Falsos positivos sin protección del entorno.** | La cámara no tiene `roi` configurado (columna vacía); el modelo ve todo el cuadro (cables, fondo). No se descartan cajas fuera de la cama aunque ya haya calibración. No hay enfriamiento tras una reanudación (podría pausar en bucle). | `cameras.roi` nulo; `model._postprocess` sin filtro espacial |
| G9 | **Nadie se entera si la web no está abierta.** | El único aviso es el banner web; sin cliente conectado, no hay sonido ni mensaje, y en `on` la pausa se ejecuta sin que nadie la haya visto. | solo `manager.broadcast` |
| G10 | **El usuario no puede etiquetar** un incidente como acierto o falso positivo. | Sin esa etiqueta, la tasa de a.3 no se puede calcular sino a mano. | no existe |
| G11 | **La telemetría no se usa para decidir.** | El puntaje combinado (modelo + telemetría) «solo se muestra»; pesos 0,6 / 0,3 / 0,15 sin calibrar. | `fusion.py`, `KNOWN_LIMITATIONS.md` §9 |
| G12 | **El tiempo restante en un instante no se guarda**: se recalcula en la web con `print_duration` y el total del laminador; para un incidente hay que reconstruirlo. | reconstruible con las muestras (`extra["print_stats.print_duration"]`) y `geometry.file.estimated_time` | `lib/eta.ts`, `jobFacts.ts` |
| G13 | **La pausa de Creality mueve el cabezal** (`PAUSE_EXTERNAL`: sube la Z a ~50 mm y aparca); con una pieza ya enredada no se ha medido qué pasa. | sin medir | `docs/laboratorio/descubrimiento/macros.cfg` |
| G14 | **Cámara:** la cámara de prueba no mostraba la pieza; con la C922 hay que colocarla, calibrarla y probar que el modelo ve la pieza. | ver `PROGRESO_FINAL.md` | pendientes de laboratorio |

### b.4 Lo que ya sirve para el Paso 2 (datos disponibles para la pantalla de Incidente)

- **Foto con cajas:** `layer_captures.image_path` (archivo) y `detections.raw_output` (cajas y `frame`/`roi`, normalizadas).
- **Clase, confianza, capa y hora:** `detections`, `layers.detected_at`, y el evento `auto_pause.would_pause`.
- **Estado completo de la impresora en ese instante:** `telemetry_samples` (1 Hz, con `extra`) y `layers.telemetry`.
- **Línea de tiempo con origen:** `printer_events` por trabajo, con verificación de cadena.
- **Reporte PDF:** `GET /print-jobs/{id}/report.pdf`.
- **Reanudar:** `POST /printers/{id}/resume` con la guarda. **Cancelar: falta (G3).**

---

## c) Propuesta de regla de «inminente» (sin implementar)

**Idea:** una regla por clase con tres ingredientes: persistencia en el tiempo, evidencia espacial coherente y una
confianza por clase. La telemetría baja el listón de persistencia, nunca dispara sola.

### c.1 Entradas por foto

Para cada foto: lista de cajas (clase, confianza, posición normalizada) del modelo; la posición en la cama si la cámara
está calibrada (para descartar cajas fuera de ella); y el puntaje de telemetría (`fusion`) como información.

### c.2 Reglas por clase (parámetros iniciales *propuestos*, a calibrar en `warn`)

| Clase | Persistencia | Confianza mínima | Acción |
|---|---|---|---|
| `spaghetti` | **3 fotos seguidas** con la clase, todas ≥ 0,25 y **al menos una ≥ 0,50** | — | Pausa (cuenta de 15 s) |
| `layer_shift` | **2 fotos seguidas** con confianza ≥ 0,60 | — | Pausa (cuenta de 15 s) |
| `warping` | **5 fotos** con la clase y la caja que **crece o se queda** (IoU ≥ 0,3 entre fotos) | ≥ 0,50 | Alerta; pausa solo con confirmación humana o si además aparece `spaghetti` |
| `under_extrusion` | 3 capas (igual que hoy) | ≥ 0,25 | Alerta crítica (sin pausa) |
| `stringing`, `blob_over_extrusion` | — | — | Solo se muestran |

### c.3 Condiciones que se suman a todas

1. **Coherencia espacial:** las cajas de la racha deben **solaparse** (IoU ≥ 0,3) entre fotos consecutivas, o crecer; el
   mismo punto del entorno (un cable, la pantalla) se descarta si aparece también en fotos sanas anteriores.
2. **Solo dentro de la cama:** con la cámara calibrada, la caja debe caer sobre la cama o en el espacio sobre ella;
   y se configura el `roi` de la cámara para no mirar lo que no importa (G8).
3. **Tiempo además de capas:** la persistencia se cumple al llegar a 3 fotos **o** al pasar **90 s** con el defecto
   visible en las fotos tomadas (se añadirían fotos cada ~30 s si la capa es lenta); lo primero que ocurra (G6). La
   cuenta de 15 s se mantiene.
4. **Telemetría:** si el puntaje combinado es ≥ 0,6 (p. ej. flujo cambiado, boquilla fuera de objetivo), la
   persistencia baja un nivel (3 → 2). Si hay una **falla dura** (error de Klipper, sensor de filamento sin filamento,
   temperatura fuera de banda más de 20 s), se **registra el incidente** sin pausar (la impresora ya reacciona sola).
5. **Enfriamiento tras reanudar:** después de una reanudación se exige el doble de persistencia durante 10 capas, para
   no entrar en bucle de pausas.
6. **Idempotencia:** un incidente por racha; mientras haya uno abierto no se abre otro del mismo trabajo y clase.

### c.4 Qué hace al cumplirse la regla

1. Abre el **incidente** (registro único, a.5) con la evidencia.
2. **`warn`:** solo lo registra y anuncia. **`on`:** cuenta de 15 s y `pause`; registra la cuenta, el aborto y el envío
   en la bitácora (G2), y **confirma** que Klipper llegó a `paused` (G4); si no llega en 20 s, lo marca como
   «pausa no confirmada» y alarma.
3. La decisión humana (reanudar, cancelar, ignorar) y la etiqueta (acierto o falso positivo) cierran el incidente.

### c.5 Cómo se calibra

Con las impresiones en `warn` (a.7): con cada `would_pause` etiquetado se calcula la tasa por foto *p* y por hora; se
sube el umbral de confianza o la persistencia por clase hasta cumplir a.3, y se baja si se pierden fallos reales
(a.4). No se activa `on` por clase hasta que esa clase cumpla ambas.

### c.6 Riesgos y límites de la propuesta

- Los parámetros de c.2 son **puntos de partida sin datos reales**; sin impresiones etiquetadas con la cámara final no
  hay forma honesta de afirmar que cumplen a.3.
- La coherencia espacial y el filtro de cama dependen de una **calibración buena** de la cámara (hoy no la hay para la
  C922).
- Cualquier pausa real lleva a la reanudación de Creality, aún sin validar (Etapa C).

---

## Decisiones que necesito de Samuel para pasar al Paso 2

1. ¿Aceptas (o cambias) los objetivos de a.2, a.3 y a.4 (3 min, ≤ 1 falso por 20 h, 0 pausas falsas en 10 impresiones
   sanas, recall ≥ 80 %)?
2. ¿La pantalla de «Incidente» debe mostrar **Cancelar** aunque hoy no existe? Para eso habría que crear un endpoint
   y una guarda (solo si la impresora dice `printing` o `paused`, confirmación doble y una sola orden a la vez), con
   pruebas en la simulada. Sin eso, el botón no puede existir.
3. ¿Qué eventos abren un incidente en el Paso 2? Tal como lo pediste: `auto_pause.would_pause`, una pausa real, o una
   detección sobre el umbral. Propongo añadir también el aborto de la cuenta como parte del incidente (G2).
4. ¿El Paso 2 incluye registrar `auto_pause.pending`/`aborted` en la bitácora y confirmar `paused` (G2 y G4)? Son
   cambios pequeños y necesarios para que el incidente tenga la línea de tiempo completa; propongo que sí.
5. La regla de la sección c no se implementa en el Paso 2 (la pantalla usa la regla actual, 3 capas de *spaghetti*);
   queda para un paso posterior, después de recoger datos en `warn`.

## Lo que haría el Paso 2 (resumen)

Una pantalla «Incidente» en la web, abierta por `auto_pause.would_pause`, una pausa real o una detección sobre el
umbral, con: foto de la capa con las cajas, clase, confianza, capa y hora; el estado completo de la impresora en ese
instante; la línea de tiempo de eventos con su origen; el enlace al reporte PDF; y los botones Reanudar (con la
guarda existente) y Cancelar (nuevo, con su propia guarda). Con pruebas, la web compilando, revisión en escritorio y
celular, y datos de prueba generados en la base (un incidente simulado) **sin tocar ninguna impresora**.
