# Limitaciones conocidas

## 0. Pausa automática por spaghetti

**Estado:** implementado y verificado (con impresora simulada - URL inalcanzable a propósito, sin tocar hardware real). Ver `app/services/auto_pause.py`.

Cuando el modelo detecta `spaghetti` en **3 capas consecutivas** (mismo umbral que la alerta de atasco en `jam_detection.py` - reutilizado a propósito, no hay datos que justifiquen un número distinto; la lógica de "racha de N capas consecutivas" quedó compartida en `app/services/streak_detection.py`), se programa una pausa automática con una **ventana de gracia de 15 segundos** (`_GRACE_PERIOD_SECONDS` en `auto_pause.py`) antes de mandar el comando real a la impresora. El frontend muestra un banner global (no depende de qué pantalla esté abierta) con cuenta regresiva calculada desde `executes_at` que manda el backend, y un botón para abortar.

**Modo de la pausa automática (`AUTO_PAUSE_MODE` en el `.env`).** `on` (por defecto): el comportamiento descrito. `warn`: se anuncia en la web (banner «Modo aviso: habría pausado…») y se registra en la bitácora un evento `auto_pause.would_pause` (origen `monitor`, con la capa, la confianza del modelo, las tres capas de la racha y `sent: false`), pero **no se envía nada a la impresora** ni se cuenta regresivamente: sirve para contar cuántas veces habría pausado. `off`: no hace nada. Un valor distinto impide que el backend arranque. Se lee al arrancar: cambiarlo exige reconstruir o reiniciar el backend. Aun en `warn` y `off` la guarda interna de `_execute` jamás envía la pausa si el modo no es `on`.

**Dónde vive el estado "pausa pendiente":** en memoria, en el proceso del backend (`AutoPauseManager._pending`), no en Postgres. La cuenta regresiva ya es una `asyncio.Task` corriendo en ese proceso sin importar dónde se registre "hay una pendiente", así que guardarlo ahí evita una segunda fuente de verdad. La contra: **si el backend se reinicia a mitad de la ventana de gracia, la pausa pendiente se pierde en silencio** - no se ejecuta, y tampoco queda registro más allá de los logs de esos 15 segundos. Se aceptó ese riesgo porque la ventana es corta y esto es una función de seguridad/demo, no infraestructura que necesite sobrevivir un reinicio. Si esto preocupa para producción, la forma de arreglarlo es persistir la pausa pendiente en Postgres y reconciliarla al arrancar el backend (ejecutarla de inmediato si el plazo ya venció, o reprogramar el resto).

**Mejora evaluada y descartada (2026-10-08): reevaluar la racha al arrancar el backend.** Parece lo más simple (al iniciar, mirar cada trabajo abierto y reprogramar la cuenta regresiva si las últimas 3 capas son spaghetti), pero el **aborto del usuario también vive solo en memoria**: tras un reinicio no se puede distinguir una pausa que se perdió de una que el usuario abortó a propósito, y la pausa se volvería a disparar sin que nadie la espere, sobre una impresión que alguien decidió dejar seguir. Es peor que el límite actual. La forma correcta sigue siendo persistir en Postgres los estados "pendiente" y "abortada" y reconciliar al arrancar (requiere una migración). Un reinicio a mitad de impresión no es hipotético: el 2026-10-08, con la impresión en curso, Docker en WSL2 reinició el backend 3 veces en 2 minutos porque faltaba la sesión `wsl -- sleep infinity`.

**Caso límite probado de verdad:** conexión caída al intentar pausar. Se armó una impresora de prueba con `octoprint_url` apuntando a una IP inalcanzable a propósito y se dejó correr la ventana completa sin abortar. Resultado real (de los logs):

```
23:06:11  Spaghetti streak (3 consecutive layers)... auto-pause scheduled for 23:06:11... unless aborted
23:06:12  Executing auto-pause for job 36 (printer 37) via Moonraker at http://192.168.10.250:7125
23:06:14  ERROR Auto-pause HTTP call to Moonraker failed for job 36 (printer 37)
```

El sistema **no falla en silencio**: publica `auto_pause.failed` y el frontend muestra un banner rojo de error explícito ("No se pudo contactar a la impresora para pausarla"). Pero importante: **si esto pasa de verdad, la impresora sigue imprimiendo sin que nadie la haya pausado** - el auto-pause es una red de seguridad que puede fallar igual que cualquier llamada de red, y en ese caso hace falta intervención manual (pausar desde la propia impresora). No hay reintento automático.

**Caso límite no resuelto, y no inventado:** cuánto tiempo es seguro dejar una impresión pausada sin arruinar la adherencia entre capas. Depende del material (las impresiones de prueba fueron en PETG) y de si el hotend retrae/mantiene temperatura durante la pausa (comportamiento del macro `PAUSE` configurado en `printer.cfg` de la Creality Hi, que no revisamos). No hay un número confiable para poner acá sin medirlo en la impresora real - mejor no inventarlo. Los 15 segundos de ventana de gracia son cortos comparados con cualquier riesgo de adherencia, así que el diseño actual no lo necesita, pero si en algún momento se sube ese valor bastante, esto pasa a importar.

**Verificación de los endpoints de Moonraker (`/printer/print/pause` y `/printer/print/resume`):** al implementar la pausa automática no se probaron en vivo contra la impresora real, para no arriesgar una impresión real en curso; se confió en la documentación pública y estable de Moonraker (los mismos endpoints que usan Fluidd/Mainsail). Más adelante sí se probaron a mano sobre la impresora real: la pausa funcionó (Klipper pasó a `paused` y el sistema lo reflejó solo), pero tras reanudar, la impresora terminó en error (`Move out of range: 292.424 249.610 28.401`). La causa no está determinada: los logs de ese día ya no existen en la impresora (ver `docs/laboratorio/RESULTADOS.md`, sección 4, con lo que sí se pudo afirmar y con qué certeza; análisis parcial anterior en `docs/moonraker_discovery/incidente_reanudacion.md`). Cualquier prueba nueva de pausa/reanudación conviene hacerla con una impresión corta y descartable.

**Reanudación desde la web (guardia, 2026-10-08):** no se pudo saber si la orden de aquel incidente llegó dos veces, así que el `POST /printers/{id}/resume` pasa por `app/integrations/moonraker/print_guard.py`: una sola orden a la vez por impresora (el segundo clic simultáneo recibe 409), ninguna otra en los 20 s siguientes (aunque la primera haya fallado por timeout, porque pudo llegar) y ninguna si la propia impresora (un GET de solo lectura de `print_stats.state`, no lo último que vio PrintWatch) no dice `paused`. Si no se puede leer el estado, no se manda nada (502). Esta guardia protege contra duplicados desde PrintWatch; no impide que alguien reanude desde Fluidd o la pantalla al mismo tiempo, ni explica por sí sola el error de movimiento fuera de rango.

## 1. Detección de capa: automática vía Moonraker (resuelto)

**Estado:** resuelto para las Creality Hi. El disparo manual queda como plan B.

La Creality Hi corre Klipper con Moonraker, no OctoPrint, así que el listener de `app/integrations/octoprint/` no le sirve. Ahora hay un segundo listener, `app/integrations/moonraker/listener.py`, que se conecta al WebSocket de Moonraker (`ws://<ip>:7125/websocket`), se suscribe a `print_stats` y `virtual_sdcard` (y, desde la telemetría, a los demás objetos del punto 7), y publica el mismo evento `layer_ready:{printer_id}` en Redis que publicaba el script manual. De ahí en adelante el pipeline no cambia: `capture` -> `captures:pending` -> `inference-worker` -> Postgres -> WebSocket.

Cada impresora elige su listener con la columna `printers.integration_type` (`octoprint` | `moonraker`); `PrinterListenerManager` arranca el que corresponda.

Además de las capas, el listener abre el job cuando la impresora empieza a imprimir y lo cierra cuando Klipper reporta `complete` / `cancelled` / `error`, así que una impresión no necesita ninguna intervención manual para aparecer en la timeline.

### Particularidades de la Creality Hi (verificadas contra el hardware)

Firmware observado: Klipper `09faed31-dirty`, Moonraker en el puerto 7125, ARMv7 de 2 núcleos.

1. **`print_stats.info.current_layer` siempre es `null`.** El camino estándar de Klipper (que el G-code llame a `SET_PRINT_STATS_INFO`) no aplica: el slicer de Creality no emite ese comando (verificado sobre el G-code real, 0 apariciones). En cambio emite `;LAYER_CHANGE`, y el Moonraker de Creality cuenta las capas por su cuenta y las expone en **`virtual_sdcard.layer`** y `virtual_sdcard.layer_count`, que no son campos del Moonraker estándar. El listener usa esos. **No hace falta tocar el slicer.**

2. **`print_stats.z_pos` viene desfasado.** Medido en una impresión real: se quedó clavado en 60.63 mm durante las capas 324, 325 y 326 mientras el toolhead estaba realmente en ~65.4 mm, y recién saltó 5.2 mm de golpe en la capa 327. Por eso el listener calcula la altura como `capa x layer_height` (tomando `layer_height` de la metadata del archivo), que coincide con la Z real dentro de ~0.03 mm y da exactamente `object_height` en la última capa. `z_pos` queda solo como fallback.

3. **Las notificaciones son parciales.** `notify_status_update` trae únicamente los campos que cambiaron: en una notificación de cambio de capa, `z_pos` llega en `None`. El listener mantiene el estado mezclado en memoria (`_PrinterState`); leer cada mensaje por separado no alcanza.

4. **Moonraker no pide API key en la LAN.** Por eso `octoprint_api_key` es opcional al crear una impresora, y para una Moonraker se guarda vacío.

### Limitaciones residuales

- **Se salta una capa al (re)conectar.** El listener toma la capa en curso como línea de base sin dispararla, porque ya fue capturada antes de la reconexión o la boquilla ya pasó. Reiniciar el backend en medio de una impresión cuesta, como mucho, una capa.
- **Nombres de columna heredados.** `printers.octoprint_url` y `printers.octoprint_api_key_encrypted` se siguen llamando así por compatibilidad; para una impresora Moonraker guardan su URL base (`http://<ip>:7125`) y una clave vacía. Renombrarlas es puramente cosmético y toca varias capas.
- **La altura es calculada, no medida.** Si un G-code usa una primera capa más gruesa que el resto, todas las alturas quedan corridas por esa diferencia (décimas de mm). No afecta la detección, solo el dato mostrado.

### Plan B: disparo manual

`backend/scripts/mark_layers.py` sigue funcionando y **no hay que borrarlo**: sirve si el listener falla durante una demo, o para impresoras sin Moonraker accesible. Registra el job y cada capa por la API y publica el mismo `layer_ready`.

Requisitos: Postgres, Redis y backend arriba (ver punto 2) y la cámara conectada.

1. Terminal A, desde la raíz del proyecto (dejar corriendo `capture` toda la impresión):

   ```powershell
   capture\.venv\Scripts\python.exe -m capture.main
   ```

2. Terminal B:

   ```powershell
   cd backend
   .\.venv\Scripts\python.exe scripts\mark_layers.py --printer-id 35 --layer-height 0.2
   ```

   Pide usuario y contraseña de un usuario **admin** (o definí `PRINTWATCH_USER` y `PRINTWATCH_PASSWORD` en esa terminal). Si la impresora ya tiene un job en curso, pregunta si continuarlo o cancelarlo y empezar uno nuevo.

3. Durante la impresión:

   | Entrada | Acción |
   |---|---|
   | Enter | marca la capa siguiente y dispara la captura |
   | `<n>` o `<n> <z>` | marca la capa `n` (z opcional, en mm) |
   | `r` | reenvía el disparo de la última capa (por ejemplo si `capture` no estaba corriendo) |
   | `f` / `x` | cierra el job como completado / fallido (pide confirmación) |
   | `q` o Ctrl+C | sale sin cerrar el job; al volver a correr el script se puede continuar |

Opciones útiles: `--step N` (cuántas capas avanza cada Enter), `--first-layer-height`, `--file-name`.

**Importante:** si el listener de Moonraker está activo para esa impresora, las dos fuentes van a registrar capas sobre el mismo job. No es destructivo (la capa duplicada se ignora por la restricción única), pero para usar el plan B conviene apagar el listener, por ejemplo poniendo `integration_type = 'octoprint'` en esa impresora y reiniciando el backend.

## 2. Docker en WSL2 necesita una sesión de WSL abierta

Docker Engine corre dentro de WSL2 (no Docker Desktop, por Windows 10 LTSC). WSL2 apaga su VM cuando no queda ninguna sesión abierta, y con ella se detienen los contenedores y los puertos publicados en `localhost` (Postgres, Redis, backend). Mientras dure una impresión hay que mantener una sesión de WSL viva, por ejemplo una terminal con `wsl -- sleep infinity`. Al arrancar de nuevo, `restart: unless-stopped` levanta los contenedores solos, pero tardan unos segundos en quedar `healthy`.

Esto ya pasó dos veces entre sesiones de trabajo: el síntoma es `ConnectionRefusedError` al puerto 5432 desde Windows.

## 3. La VPN (HotspotShield) rompe el acceso a las impresoras

Con HotspotShield activo, el listener deja de conectarse a Moonraker aunque la impresora esté encendida y en la misma red. El cliente instala las rutas `0.0.0.0/1` y `128.0.0.0/1` (el truco habitual para pisar la ruta por defecto sin reemplazarla) y captura también el tráfico hacia la LAN: las conexiones a `192.168.10.22` salen por el adaptador `HotspotShield WinTun` (origen `100.127.255.253`) en vez de por la Wi-Fi.

**Síntomas** (confunden, porque no parecen de red):

- `websockets.legacy.exceptions.InvalidMessage: did not receive a valid HTTP response` en el log del backend, cada 10s.
- `curl http://<ip>:7125/printer/info` devuelve `Empty reply from server`: el TCP conecta pero no llega respuesta.
- Un escaneo de puertos da **todos los puertos abiertos en todas las IPs**, incluido el router. Esa es la señal delatora: la VPN acepta cualquier conexión y después la descarta.

**Solución:** desconectar HotspotShield mientras se usa el sistema, o activar su opción de excluir la red local (split tunneling). Conviene verificarlo antes de cualquier demo: `curl http://192.168.10.22:7125/printer/info` tiene que devolver el JSON de Klipper.

## 4. Alertas automáticas solo para atasco

Hoy la única regla que crea alertas automáticamente es la de atasco (`under_extrusion` en capas consecutivas, `backend/app/services/jam_detection.py`). Una detección aislada (por ejemplo `spaghetti`) queda registrada en `detections` con `has_defect = true`, pero no genera una alerta por sí sola.

## 5. Vista en vivo con cajas de detección: desfase de ~1-2s y formato histórico distinto

**Estado:** implementado y verificado con hardware real (`Creality Hi-3422`, capas 325-355 del job "cerebro").

El detalle de impresión (`/printers/:id/jobs/:id`) ahora muestra la cámara en vivo con las cajas de la última detección dibujadas encima (clase + confianza, color por clase), mientras el job está `running`. Nuevo evento WebSocket `detection.boxes` (canal `events:detection_boxes`), separado de `detection.result` a propósito: la timeline no necesita el detalle por caja, y así ningún consumidor existente tuvo que cambiar.

**Desfase esperado (no es un bug):** `capture` guarda la foto y actualiza `latest_frame:{camera_id}` en cuanto termina de fotografiar; `inference-worker` recién corre el modelo después. Entre esos dos momentos (~1-2s, medido en la prueba real) el video ya muestra el frame de la capa nueva pero las cajas dibujadas siguen siendo las de la capa anterior. Se corrige solo en cuanto llega `detection.boxes` de la capa nueva — no hace falta ninguna acción, pero vale saberlo si se lo mira con lupa.

**Corregido de paso:** las cajas que ya calculaba el modelo (`inference/model.py`) se guardaban en `detections.raw_output` en un formato sin normalizar e inconsistente con el que usan los scripts de diagnóstico (`calibrate_thresholds.py`, `inspect_false_positives.py`). Nada las leía todavía, así que no se había notado. Ahora se guardan igual que esos scripts (`[x1,y1,x2,y2]` normalizado 0..1). Las **16 detecciones creadas antes de ese cambio** (impresora 35, 22-09-2026) quedaron con el formato viejo en `raw_output.detections[].box` — inofensivo porque nada las lee retroactivamente, pero si alguna vez se recorre `raw_output` histórico hay que tenerlo en cuenta.

**Verificado:** cajas alineadas correctamente sobre la foto real (confirmado dos veces — dibujado manual con OpenCV y captura de pantalla del navegador real, ambos coinciden), reescalado 640×640 → 1280×720 correcto, cámara con ROI sin configurar hoy pero el cálculo ya contempla el caso con ROI activo, y una capa sin defecto deja el canvas vacío sin cuadros pegados de la anterior.

## 6. Falsos positivos de `stringing` en piezas de geometría orgánica

Observado en la impresión real del cerebro (job 34): el modelo marcó `stringing` con confianza 0.41-0.44 en capas consecutivas sanas. La pieza tiene muchas hebras finas y curvas que visualmente son casi idénticas a los hilos que el modelo busca. Con el umbral actual (0.25) esas detecciones pasan.

No afecta a las alertas (ver punto 3: `stringing` suelto no genera alerta), pero sí ensucia la timeline. Si aparece en la demo, conviene mostrarlo como ejemplo honesto del comportamiento del modelo en vez de esconderlo, o subir el umbral de esa clase en particular.

## 7. Telemetría y bitácora de eventos

**Estado:** probado contra la impresora simulada y, desde el 2026-10-08, **observado con la Creality Hi real imprimiendo** (muestras, sensores, bitácora estable y cadena íntegra; ver `docs/laboratorio/RESULTADOS.md`). Sin comprobar con la real: la atribución a consola/archivo/externo (exige órdenes) y la secuencia de inicio de una impresión. Antes: (ver `docs/PROGRESO_TELEMETRIA.md`).

El listener de Moonraker guarda una muestra por segundo (posición, velocidad, temperaturas y potencia de boquilla y cama, ventilador, factores de velocidad y flujo, desfase de Z, progreso, filamento y los sensores extra que tenga la impresora) mientras hay un trabajo abierto, guarda con cada capa una foto de esos valores y registra en la bitácora los cambios de estado y las intervenciones (temperaturas objetivo, velocidad, flujo, ventiladores, desfase de Z, objetos excluidos, sensores de filamento, comandos de consola) con su origen.

- **Volumen medido en la Hi real (2026-10-08) y, antes, en la simulada:** el WebSocket dio 4,2 KB/s con 45 objetos (1.491 mensajes en 300 s; la suscripción de PrintWatch es menor), el backend 0,35 % de un núcleo y 115 MiB, y Postgres 1.036 bytes por muestra (714 de ellos el campo de sensores extra; la Hi tiene 5 sensores de filamento): ~7,5 MB por cada 2 h de impresión, antes de quitar las claves constantes `enabled`. En la simulada fueron ~2 KB/s, 0,08 % y ~2,7 MB. Lo anterior era: ~2 KB/s de WebSocket, 0,08 % de un núcleo para el listener y ~2,7 MB en Postgres por impresión de 2 h. La Hi puede reportar más o menos campos; se confirma con `moonraker_discovery.py --only-ws` durante una impresión.
- **Sin trabajo abierto no se guarda serie.** La lectura en vivo (evento `telemetry.sample` y `/printers/{id}/telemetry/latest`) sigue llegando, pero no queda histórico fuera de las impresiones. La última lectura vive en la memoria del backend: tras un reinicio vuelve en ~1 s si la impresora está conectada.
- **Las muestras se insertan en lotes de 10.** Si la base falla, ese lote se pierde (como mucho ~10 s de telemetría) y queda anotado en el log.
- **Qué se puede saber del origen de un cambio y qué no** (`app/integrations/moonraker/interventions.py`). Cada cambio se atribuye solo con evidencia:
  - `printwatch`: PrintWatch mandó la orden (pausa automática o botones de la web) y el cambio llegó en los 60 s siguientes. Si la orden falló por timeout pero la impresora cambió igual, se atribuye a PrintWatch con el error en el detalle, porque la orden pudo haber llegado.
  - `console`: un comando de G-code que explica el cambio aparece en el registro de consola de Moonraker (`/server/gcode_store`, consultado cada ~2 s). Ahí quedan la consola de Fluidd/Mainsail y los controles que mandan G-code (velocidad, flujo, babystepping, excluir objeto). Si la pantalla de la impresora usara esa misma API, también saldría como `console`.
  - `gcode_file`: una línea del archivo que se imprime, o de una macro que esa línea llama (como `START_PRINT` o `END_PRINT`), explica el cambio y está en el tramo del archivo que Klipper estaba leyendo. Para saberlo el backend descarga el archivo una vez por impresión, con GET y a 1 MB/s como máximo (`GCODE_SCAN_ENABLED=false` lo apaga; entonces esos cambios salen como `external`).
  - `external`: sin evidencia. **No distingue** entre la pantalla de la impresora, los botones de pausa/reanudar/cancelar de Fluidd (usan una API que no deja rastro en la consola) u otra aplicación. El inicio de cada impresión sale así por la misma razón. Se marca "externo" en vez de inventar un origen.
  - `printer`: errores de Klipper, fin del archivo, sensor de filamento y estado de Klippy. `monitor`: conexión y desconexión de PrintWatch con la impresora.
- **La atribución al archivo es heurística.** De las macros solo se resuelven los `{params.X}`; cualquier otra expresión de la plantilla y todas las ramas de un `{% if %}` cuentan como "puede cambiar este valor". La posición se compara en bytes con 256 bytes de tolerancia; si Klipper contara caracteres y el archivo tuviera muchos comentarios con tildes, la posición podría correrse.
- **Ventiladores:** en la Hi no existe el objeto `fan`; el ventilador de capa es `output_pin fan0` (se guarda en la telemetría, pero sus cambios no se vigilan en la bitácora). Los cambios programados en el archivo no se registran (los laminadores los cambian todo el tiempo; la curva está en la telemetría), y los que no tienen explicación solo se registran si se pudo revisar el archivo; sin él, la mayoría serían falsos "externos".
- **Los eventos sin evidencia inmediata se registran con demora:** esperan ~5 s por si aparece el comando de consola, y hasta 3 min si el archivo todavía se está indexando. La hora guardada es la del cambio, no la del registro, así que el orden de la cadena puede no coincidir con el cronológico.
- **Hora de los comandos de consola:** Moonraker los marca con el reloj de la impresora; se corrigen con la diferencia de relojes estimada a partir del encabezado `Date` de sus respuestas (resolución de 1 s, se afina con cada consulta). Al principio de una conexión puede haber medio segundo de error, y un comando puede aparecer justo después del cambio que provocó.
- **Lo escrito en la consola antes de que PrintWatch se conectara no se registra** (la primera consulta solo marca el punto de partida).
- **La cadena de hashes no lo detecta todo.** Detecta un evento editado o borrado en medio de la bitácora (`/printers/{id}/events/verify`), pero no el borrado de los últimos eventos ni una reescritura completa por alguien con acceso de escritura que recalcule todos los hashes. Para cubrir eso hay que guardar el último hash fuera de la base, por ejemplo impreso en el informe del trabajo.
- **Reinicios de Klipper:** para no depender de si Moonraker restaura la suscripción cuando Klippy se reinicia, el listener registra el aviso (`notify_klippy_*`), se reconecta y se vuelve a suscribir.
- **Valores con ruido de redondeo:** las columnas son `REAL` (4 bytes, ~7 cifras significativas); la API redondea a 4 decimales al leer.

## 8. Mapa de la cama: precisión de la ubicación de los defectos

**Estado:** backend implementado y probado contra la cámara simulada y calibrado dos veces el 2026-10-08, pero con una **cámara USB genérica provisional, no con la C922** (confirmado por Samuel el 2026-10-09; la C922 será la cámara de la implementación final). Esas dos calibraciones no valen para la C922: hay que recalibrar con ella (ver `docs/laboratorio/PROGRESO_FINAL.md`, «Aclaración sobre la cámara»).

Cómo funciona (`app/services/bed_map.py`): el usuario marca las cuatro esquinas de la cama sobre una foto de la cámara. Eso da la homografía imagen-cama; de ella se estima la focal y la posición de la cámara, y con eso cada caja de defecto se lleva a milímetros de la cama corrigiendo el paralaje con la altura de la capa. La Creality Hi es de cama móvil: si la cámara está fija al marco o a la mesa, la cama se desplaza en la imagen y se compensa con la posición Y del cabezal en la foto de la capa. Contra la cámara simulada, el error es menor a 1 mm; en la real hay que sumar:

- **El tamaño de la cama no es el recorrido de los ejes:** Klipper reporta X −19..285 e Y −7..273 en la Hi (incluye el cortador de filamento, en X 279,6); la cama es de 260 × 260 y la malla va de 10 a 250. Medido con la impresora real. El tamaño se toma ahora de la malla (10 + 250); sin malla, 260 mm sin pasar del recorrido. Antes se tomaba el recorrido y la calibración habría quedado torcida.
- **Las marcas a mano:** se estima ~1,5 % del tamaño de la cama (~4 mm).
- **La distorsión del lente**, que no se modela. Una webcam gran angular, como la C922, deforma un poco los bordes de la imagen; cerca de las esquinas puede sumar varios milímetros (no medido: todavía no hay calibración con la C922).
- **La altura supuesta:** se asume que el defecto está en la superficie de la capa actual. Un hilo de spaghetti que cayó a la cama queda sobrecorregido.
- **La sincronización en cama móvil:** la foto y la posición del cabezal pueden estar desfasadas hasta ~0,3 s (Klipper informa cada 250 ms y el video va a ~6 cuadros/s). El error crece con la velocidad de la cama en Y (a 200 mm/s, ~60 mm); por eso cada capa guarda esa velocidad, estimada con posiciones consecutivas. Cada ubicación lleva su error estimado; las de más de 20 mm se muestran como poco confiables (círculo punteado del tamaño del error) y no entran al mapa de calor. En el modo demostración, los defectos detectados justo al cambiar de capa quedaron con ±40-50 mm: en ese instante el cabezal viaja al inicio de la capa y la cama se mueve en Y a 140-170 mm/s. La ubicación calculada era exacta (la demostración conoce la verdad), pero el sistema no puede saberlo y la marca como poco confiable.
  - *Mejora propuesta (no implementada):* que `capture` guarde la hora exacta de cada cuadro y que el backend conserve las posiciones a 4 Hz de los últimos segundos para interpolar la posición en esa hora. Bajaría el error a la latencia de la cámara (~0,1 s, sin medir). Requiere verificar antes que el reloj de WSL2 y el de Windows coincidan (WSL2 puede desfasarse después de suspender el equipo).
- **La estimación de la cámara** supone píxeles cuadrados y el centro óptico en el centro de la imagen. Si la vista es casi perpendicular a la cama, la focal no se puede despejar y se usa el campo de visión típico de una C922 (78° en diagonal, unos 907 px a 1280×720), que es la cámara prevista para la implementación final; con otra cámara la focal es otra (la genérica provisional dio ~1.500 px, un campo de ~52°). La web lo avisa.
- **Si la cámara se mueve hay que recalibrar.** Se guarda el historial: cada detección se ubica con la calibración vigente cuando se capturó (o con la primera posterior, si no había ninguna antes, suponiendo que la cámara no se había movido).
- **Detecciones anteriores:** las cajas de las primeras 16 detecciones (formato viejo, en píxeles) no se pueden ubicar y se cuentan aparte. Las detecciones previas a este cambio no guardaban el ROI; se asume el cuadro completo, que es lo que se usó siempre (nunca se configuró un ROI).
- **Antigüedad de la foto para calibrar:** `capture` ahora guarda la hora de cada cuadro y el backend la informa (`X-Frame-Age-Seconds`); hay que reiniciar `capture` para que empiece a hacerlo. Sin eso, la foto puede ser la última que quedó en Redis de una sesión anterior.

## 9. Análisis derivados: puntaje combinado, salud, reporte y costo

**Estado:** implementados y probados con datos sintéticos y con la impresora simulada; ninguno se ha contrastado con impresiones reales de la Creality Hi (todavía no hay trabajos con telemetría real). En la web y en el reporte llevan la marca "Estimación" con la explicación de cómo se calculan.

**Puntaje combinado (modelo + telemetría, `app/services/fusion.py`).** Solo se muestra: las alertas y la pausa automática siguen usando únicamente el modelo.

- **Los pesos son iniciales, no calibrados.** Cada señal (boquilla fuera del objetivo, calentador al máximo, flujo cambiado, cama bajada, sensor de filamento...) sube el puntaje con un peso fijo según qué tan directa es su relación con el defecto (0,6 / 0,3 / 0,15). Los umbrales sí tienen respaldo (la banda de ±5 °C que Klipper considera en rango, el paso de 5 % de la calibración de flujo), pero cuánto debe pesar cada señal solo se puede ajustar con impresiones reales etiquetadas.
- **Solo puede subir el puntaje.** Una telemetría normal no es evidencia en contra (un atasco parcial no se ve en los sensores), así que el puntaje no sirve para descartar falsos positivos del modelo.
- **No todas las clases tienen señales.** El spaghetti y, casi, el desplazamiento de capa no tienen una lectura de la impresora que los explique; su puntaje es el del modelo.
- **La ventana es la capa recién impresa** (más hasta dos anteriores si tiene menos de 10 muestras). En capas muy rápidas (pocos segundos) la ventana puede quedar con menos muestras; en trabajos sin telemetría por segundo se usa la foto de telemetría de la capa.
- **No distingue el origen del cambio.** Un flujo bajado por el archivo cuenta igual que uno bajado desde la consola: lo que importa para el defecto es el valor.
- **El sensor de filamento:** la Hi expone cinco (`filament_sensor` del cabezal, `_2` y tres de la caja CFS). Los de la caja marcan "sin filamento" todo el tiempo cuando la caja no está conectada, así que solo cuenta un sensor que haya visto filamento en ese trabajo (con la lógica anterior habrían sumado +0,6 a toda sub-extrusión). Si algún día se conecta la caja, sus ranuras vacías seguirían sin contar.

**Salud de la impresora (`app/services/health.py`).**

- **Necesita historia:** al menos 6 trabajos terminados con telemetría y con el mismo objetivo de temperatura (5 de línea base y 1 para comparar). Con la impresora real eso tomará varias semanas de uso.
- **"Normal" es lo que la impresora hizo antes**, no un valor de catálogo. Si la impresora ya venía mal cuando se formó la línea base, eso queda como normal.
- **Factores que cambian la potencia y no son desgaste:** la temperatura del cuarto, el ventilador de capa, la velocidad (más plástico que fundir), el material y una puerta o tapa abierta. Conviene leer la tendencia junto con esos datos; la comparación ya separa por objetivo de temperatura.
- **Las reglas de la carta de control** (±3σ, 2 de 3 más allá de 2σ, 8 seguidos del mismo lado) suponen mediciones independientes y con ruido parecido al normal; con pocos trabajos la desviación de la línea base es poco precisa. Cuando la línea base casi no varía, se usa como mínimo la resolución del dato para no convertir diferencias ínfimas en anomalías.
- **La velocidad de calentamiento solo se mide en arranques en frío** (cuando la impresión empieza por debajo del 20 % del camino entre 25 °C y el objetivo). Si se precalienta antes de lanzar la impresión, ese trabajo no aporta el dato.
- **Costo:** la primera consulta después de reiniciar el backend lee las muestras de cada trabajo (hasta 100 trabajos); los resultados de los trabajos terminados quedan en memoria. Medido en la simulada: ver `docs/PROGRESO_TELEMETRIA.md`.

**Reporte PDF por trabajo (`app/services/report.py`).**

- **Se genera al pedirlo, con los datos de ese momento.** No se archiva solo al terminar el trabajo: si después se reconoce una alerta o se recalibra la cámara, un reporte nuevo lo refleja. Para conservar una versión, hay que descargarla.
- **El hash impreso solo protege si el PDF se guarda fuera de la base.** Sirve para comprobar después que la cadena de eventos sigue conteniendo ese hash (que nadie borró los últimos eventos ni la reescribió entera).
- **Gráficas reducidas** a 600 puntos (promedios por tramos) y bitácora limitada a 150 eventos por reporte; el resto está en la web.
- **Texto en Latin-1** (fuentes básicas de PDF, sin incrustar tipografías): el español sale completo, pero símbolos como σ o → se escriben con letras.
- **Tiempo estimado:** la Hi **no publica `estimated_time`** en ningún objeto ni en los metadatos (medido en la impresora real); Creality Print lo escribe en el nombre del archivo (`..._PETG_6h0m27s.gcode`) y de ahí se toma, marcado como tal en la web y el reporte. Un archivo con otro nombre no tiene estimación y el reporte lo dice. Solo existe para los trabajos posteriores a este cambio.

**Costo estimado (`app/services/costs.py`).**

- **Filamento:** es lo que la impresora mandó extruir (`print_stats.filament_used`), no un pesaje. Incluye purgas y líneas de limpieza que estén en el archivo; no incluye lo que se pierde fuera de él. Los gramos salen de los gramos por milímetro del laminador si el archivo los trae; si no, de una densidad típica por material (PLA 1,24; PETG 1,27; ABS 1,04; ASA 1,07; TPU 1,21 g/cm³) y el diámetro configurado.
- **Energía: solo los calentadores**, como PWM × potencia nominal. No cuenta motores, ventiladores, electrónica, pantalla ni cámara (decenas de vatios), ni el consumo en espera. La potencia de la cama depende del voltaje: 1000 W a 220 V según la ficha, ~300 W a 120 V (supuesto de la configuración por defecto) y ~250 W a 110 V. Los huecos de más de 5 s en la telemetría no se cuentan.
- **Precios únicos** para toda la instalación (no por material ni por impresora), configurables en la web por un administrador. Hasta que alguien los configure, son valores de ejemplo y la web lo avisa.
- **En la analítica** el costo de cada trabajo se calcula con una muestra = 1 s (la frecuencia del muestreo); en la página del trabajo se usa el tiempo real entre muestras. La diferencia es mínima, pero las cifras pueden no coincidir al último peso.
