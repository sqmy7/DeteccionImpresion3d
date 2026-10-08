# Limitaciones conocidas

## 0. Pausa automática por spaghetti

**Estado:** implementado y verificado (con impresora simulada - URL inalcanzable a propósito, sin tocar hardware real). Ver `app/services/auto_pause.py`.

Cuando el modelo detecta `spaghetti` en **3 capas consecutivas** (mismo umbral que la alerta de atasco en `jam_detection.py` - reutilizado a propósito, no hay datos que justifiquen un número distinto; la lógica de "racha de N capas consecutivas" quedó compartida en `app/services/streak_detection.py`), se programa una pausa automática con una **ventana de gracia de 15 segundos** (`_GRACE_PERIOD_SECONDS` en `auto_pause.py`) antes de mandar el comando real a la impresora. El frontend muestra un banner global (no depende de qué pantalla esté abierta) con cuenta regresiva calculada desde `executes_at` que manda el backend, y un botón para abortar.

**Dónde vive el estado "pausa pendiente":** en memoria, en el proceso del backend (`AutoPauseManager._pending`), no en Postgres. La cuenta regresiva ya es una `asyncio.Task` corriendo en ese proceso sin importar dónde se registre "hay una pendiente", así que guardarlo ahí evita una segunda fuente de verdad. La contra: **si el backend se reinicia a mitad de la ventana de gracia, la pausa pendiente se pierde en silencio** - no se ejecuta, y tampoco queda registro más allá de los logs de esos 15 segundos. Se aceptó ese riesgo porque la ventana es corta y esto es una función de seguridad/demo, no infraestructura que necesite sobrevivir un reinicio. Si esto preocupa para producción, la forma de arreglarlo es persistir la pausa pendiente en Postgres y reconciliarla al arrancar el backend (ejecutarla de inmediato si el plazo ya venció, o reprogramar el resto).

**Caso límite probado de verdad:** conexión caída al intentar pausar. Se armó una impresora de prueba con `octoprint_url` apuntando a una IP inalcanzable a propósito y se dejó correr la ventana completa sin abortar. Resultado real (de los logs):

```
23:06:11  Spaghetti streak (3 consecutive layers)... auto-pause scheduled for 23:06:11... unless aborted
23:06:12  Executing auto-pause for job 36 (printer 37) via Moonraker at http://192.168.10.250:7125
23:06:14  ERROR Auto-pause HTTP call to Moonraker failed for job 36 (printer 37)
```

El sistema **no falla en silencio**: publica `auto_pause.failed` y el frontend muestra un banner rojo de error explícito ("No se pudo contactar a la impresora para pausarla"). Pero importante: **si esto pasa de verdad, la impresora sigue imprimiendo sin que nadie la haya pausado** - el auto-pause es una red de seguridad que puede fallar igual que cualquier llamada de red, y en ese caso hace falta intervención manual (pausar desde la propia impresora). No hay reintento automático.

**Caso límite no resuelto, y no inventado:** cuánto tiempo es seguro dejar una impresión pausada sin arruinar la adherencia entre capas. Depende del material (las impresiones de prueba fueron en PETG) y de si el hotend retrae/mantiene temperatura durante la pausa (comportamiento del macro `PAUSE` configurado en `printer.cfg` de la Creality Hi, que no revisamos). No hay un número confiable para poner acá sin medirlo en la impresora real - mejor no inventarlo. Los 15 segundos de ventana de gracia son cortos comparados con cualquier riesgo de adherencia, así que el diseño actual no lo necesita, pero si en algún momento se sube ese valor bastante, esto pasa a importar.

**Verificación de los endpoints de Moonraker (`/printer/print/pause` y `/printer/print/resume`):** al implementar la pausa automática no se probaron en vivo contra la impresora real, para no arriesgar una impresión real en curso; se confió en la documentación pública y estable de Moonraker (los mismos endpoints que usan Fluidd/Mainsail). Más adelante sí se probaron a mano sobre la impresora real: la pausa funcionó (Klipper pasó a `paused` y el sistema lo reflejó solo), pero tras reanudar, la impresora terminó en error (`Move out of range: 292.424 249.610 28.401`). La causa todavía no está determinada y su análisis queda pendiente de los logs de la impresora (análisis parcial en `docs/moonraker_discovery/incidente_reanudacion.md`). Mientras tanto, cualquier prueba nueva de pausa/reanudación conviene hacerla con una impresión corta y descartable.

## 1. Detección de capa: automática vía Moonraker (resuelto)

**Estado:** resuelto para las Creality Hi. El disparo manual queda como plan B.

La Creality Hi corre Klipper con Moonraker, no OctoPrint, así que el listener de `app/integrations/octoprint/` no le sirve. Ahora hay un segundo listener, `app/integrations/moonraker/listener.py`, que se conecta al WebSocket de Moonraker (`ws://<ip>:7125/websocket`), se suscribe a `print_stats` y `virtual_sdcard`, y publica el mismo evento `layer_ready:{printer_id}` en Redis que publicaba el script manual. De ahí en adelante el pipeline no cambia: `capture` -> `captures:pending` -> `inference-worker` -> Postgres -> WebSocket.

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
