# Progreso: telemetría, bitácora, mapa de la cama y rediseño

Archivo de seguimiento del trabajo de telemetría. Si la sesión se corta, al retomar se lee este archivo
y `git log` antes de tocar nada.

**Regla de seguridad (no negociable):** todo el trabajo es de solo lectura sobre la impresora. No se
envía G-code ni órdenes que muevan motores, cambien temperaturas, hagan home, pausen, reanuden o
cancelen, tampoco en pruebas o calibración. La única orden que el sistema envía por su cuenta es la
pausa automática por spaghetti, que no se modifica. Lo que necesite órdenes se prueba contra la
impresora simulada (`backend/scripts/mock_moonraker.py`).

**Contexto de esta tanda:** se trabaja sin acceso a la impresora (fuera de la red del laboratorio).
Lo que necesita la impresora real queda preparado para correrlo después y anotado en
"Pendiente con la impresora".

## Estado por fase

| Fase | Estado |
|---|---|
| 0. Descubrimiento | Parte sin impresora terminada; falta correr el script en el laboratorio |
| 1. Telemetría con fecha y hora | Terminada y desplegada; falta verificarla con la impresora real |
| 2. Bitácora de intervenciones | Backend terminado y desplegado; la pantalla de la bitácora va en la Fase 4 |
| 3. Mapa de la cama | En curso: matemática y servicio listos; faltan API, despliegue y pantalla |
| 4. Rediseño de la web | Sin empezar |
| 5. Innovación | Sin empezar |

## Fase 0: descubrimiento

**Hecho:**
- Punto de restauración antes de empezar: commit `1deb2e4`.
- Análisis del incidente de reanudación del 25-09-2026 con la evidencia disponible sin la impresora
  (base de datos y respuestas de Moonraker registradas): `docs/moonraker_discovery/incidente_reanudacion.md`.
- Script de descubrimiento de solo lectura: `backend/scripts/moonraker_discovery.py`. Guarda consola,
  logs (con extractos del incidente), historial, objetos y su estado, configuración y macros, inicio y
  final de los G-code, cámara interna (imagen y cuadros por segundo), equipo y una medición del
  WebSocket por campo. Modo `--only-ws` para medir durante una impresión sin descargar nada.
- Impresora simulada: `backend/scripts/mock_moonraker.py`. Simula una impresión (cabezal, capas,
  temperaturas, objetos, malla), la consola de G-code (para simular intervenciones externas), las
  órdenes de pausa/reanudación/cancelación, un error como el del incidente y una cámara MJPEG cuya
  imagen proyecta la cama con una homografía conocida (servirá para probar la calibración de la Fase 3).
- Pruebas automáticas (`backend/tests/`, 16 pruebas): lista blanca de solo lectura, extracción del
  incidente en los logs y corrida del descubrimiento contra la simulada dentro del proceso.
- Plantilla `docs/moonraker_discovery/README.md` con la tabla de datos esperados, marcados como
  *sin verificar* salvo lo ya medido.
- Fuentes de cámara de red en `capture/` (antes eran stubs): MJPEG por HTTP y RTSP con el backend
  FFmpeg de OpenCV y timeout de 5 s. Probado contra el stream de la simulada.

**Pendiente con la impresora:** correr el script (corrida completa con la impresora sin imprimir y
`--only-ws` durante una impresión), completar el README y el análisis del incidente, y si la cámara
interna da imagen por MJPEG o RTSP, agregarla como cámara `secondary` de la impresora 35 y compararla
con la C922.

**Decisiones:**
- El script guarda primero la evidencia que se pierde (consola en memoria y logs que rotan).
- Si la impresora pide credenciales, el script se detiene y no intenta ninguna (regla del proyecto).
- Los logs completos no se versionan (pesan y traen datos del equipo); sí los extractos. De
  `system_info` se ocultan números de serie y direcciones MAC.
- Las URLs de cámara relativas se prueban primero en los puertos web (80 y 4408, donde las resuelve
  Fluidd) y luego en el de Moonraker; nunca se prueban URLs de otros equipos ni rutas de la API.
- La cámara interna, si se agrega, va como `secondary`: los archivos de captura se nombran por rol, así
  que dos cámaras `primary` en la misma impresora se pisarían.

## Fase 1: telemetría con fecha y hora

**Hecho:**
- Migración `c3f1a9d27b40` (escrita a mano): tablas `telemetry_samples` y `printer_events`, y columna
  `layers.telemetry`. Probada primero en la base `printwatch_test` (`alembic check` sin diferencias con
  los modelos) y aplicada a la base real el 2026-10-07, después de respaldarla en
  `storage/respaldo_antes_telemetria_2026-10-07.sql` (no se versiona).
- Listener de Moonraker: pide la lista de objetos y se suscribe a los del núcleo más los sensores y
  ventiladores opcionales que tenga la impresora (`app/services/telemetry.py`). Una muestra por segundo
  mientras hay trabajo abierto, insertada en lotes de 10. Foto de la telemetría (con el objeto que se
  imprime) en cada capa. Se reconecta si Klippy se reinicia. La lógica de trabajos y capas no cambió.
- Bitácora (`app/services/printer_events.py`): conexión/desconexión, cambios de estado con su origen
  (PrintWatch, impresora o externo) y las órdenes que manda PrintWatch, en una cadena de hashes por
  impresora. Cada evento sale también por WebSocket (`printer.event`).
- API: `GET /print-jobs/{id}/telemetry` (serie, reducida a `max_points` promediando por tramos),
  `GET /printers/{id}/telemetry/latest`, `GET /printers/{id}/events`, `GET /print-jobs/{id}/events`,
  `GET /printers/{id}/events/verify`. `GET /print-jobs/{id}/layers` incluye `telemetry`.
- Pruebas: 30 en total; las de Postgres corren contra `printwatch_test` (variable `TEST_DATABASE_URL`,
  solo acepta bases que terminen en `_test`). Una prueba de punta a punta corre el listener contra la
  simulada: capas con su foto, muestras, pausa y reanudación atribuidas a PrintWatch y cadena válida.
- Verificado también en el backend desplegado (Docker) con una impresora simulada temporal dentro del
  contenedor (impresora 41, trabajo 40), borrada después.

**Mediciones (contra la simulada; estimación para la Hi):**

| Qué | Valor |
|---|---|
| Mensajes de la suscripción | 3,9 por segundo, ~2 KB/s (~15 MB por impresión de 2 h, en la red local) |
| CPU del listener | 0,08 % de un núcleo |
| Disco | 379 B por muestra; ~2,7 MB por impresión de 2 h (7.200 muestras) |

**Decisiones:**
- **1 muestra por segundo.** Klipper reporta hasta 4 veces por segundo, pero para gráficas de
  temperatura y velocidad 1 Hz alcanza, y a 4 Hz serían ~11 MB por impresión de 2 h sin ganancia
  visible. El dato fino del momento de cada capa queda en la foto de la capa, tomada del estado en
  memoria (que sí se actualiza a 4 Hz).
- Columnas `REAL` (4 bytes): suficiente precisión para sensores y la mitad de espacio que `DOUBLE`.
  Índice `(print_job_id, ts)`. Horas en UTC (`timestamptz`); la web las muestra en hora de Colombia.
- La bitácora con su cadena de hashes se creó ya en esta fase (no en la 2) para no necesitar una
  segunda migración que recalculara hashes de filas existentes. Una cadena por impresora, serializada
  con `pg_advisory_xact_lock` para que dos escritores no usen el mismo hash anterior.
- Tipos de evento y orígenes como texto, no como enums de Postgres: agregar uno no requiere migración.
- Para atribuir pausas y reanudaciones, `send_print_action` anota cada orden en memoria
  (`command_log.py`). `auto_pause.py` no se tocó: sus órdenes se reconocen porque es el único que
  llama sin `requested_by`.

## Fase 2: bitácora de intervenciones

**Hecho:**
- Detección de cambios en los campos vigilados (`app/integrations/moonraker/interventions.py`):
  temperaturas objetivo, factores de velocidad y flujo, ventiladores, desfase de Z (babystepping),
  objetos excluidos, sensores de filamento y estado de Klippy, además de los cambios de estado.
- Atribución con evidencia (`printwatch`, `console`, `gcode_file`, `printer`, `external`; ver
  `docs/KNOWN_LIMITATIONS.md`, punto 7):
  - consola: consulta de `/server/gcode_store` cada ~2 s; cada comando nuevo queda también como evento
    `console_command`, y los errores `!!` como `gcode_error`;
  - archivo: índice de las líneas que cambian algo, con su posición en bytes, construido al empezar cada
    impresión descargando el archivo (GET, 1 MB/s como máximo) y siguiendo las macros que llama
    (`app/integrations/moonraker/gcode_effects.py`, plantillas tomadas de `configfile`).
- La cadena de hashes, la verificación y el aviso por WebSocket ya venían de la Fase 1.
- API: filtros `origin` y `event_type` en `GET /printers/{id}/events`.
- Impresora simulada más fiel: posición en bytes real dentro del G-code, cambios programados en el
  archivo (temperatura en la capa 2, ventilador en la 3), macros de inicio y fin, y `/mock/screen` para
  simular cambios desde la pantalla (sin rastro en la consola).
- Pruebas: 78. Una de punta a punta cubre un cambio de cada tipo y comprueba que los únicos "externos"
  son el inicio de la impresión y el cambio hecho desde la pantalla. Verificado también en el backend
  desplegado con una impresora simulada temporal (impresoras 42 y 43, borradas después).

**Decisiones:**
- Ninguna orden nueva a la impresora: todo es lectura (WebSocket, `gcode_store`, el archivo y
  `configfile`).
- Los cambios del ventilador programados en el archivo no se registran; sin el archivo, los del
  ventilador sin explicación tampoco (serían en su mayoría falsos "externos").
- Un evento sin evidencia espera ~5 s a la consola y hasta 3 min al índice del archivo antes de
  registrarse como `external`; la hora del evento es la del cambio.
- Los comandos de consola llevan la hora de la impresora corregida por la diferencia de relojes,
  estimada con el encabezado `Date` de las respuestas.

## Fase 3: mapa de la cama (en curso)

**Hecho (sin desplegar todavía):**
- `app/services/bed_map.py`: homografía imagen-cama a partir de 4 puntos (lo mismo que
  `cv2.findHomography` con cuatro puntos, en Python puro), estimación de la focal y la posición de la
  cámara desde esa homografía (restricciones de Zhang con una vista), corrección de paralaje con la
  altura de la capa y desplazamiento en Y de la cama (la Creality Hi es de cama móvil), con una
  estimación del error de cada ubicación.
- `app/services/defect_map.py`: ubica cada caja de defecto de un trabajo con la calibración vigente
  al capturar, la foto de telemetría de la capa y los objetos del archivo; mapa de calor por celdas.
- Migración `d4e8b2c61f05` (a mano): tabla `camera_calibrations` y columna `print_jobs.geometry`.
  Probada en `printwatch_test` (subir, `alembic check`, bajar, subir). **No aplicada aún a la base real.**
- Listener: guarda en el trabajo los límites de los ejes, la malla de la cama y los objetos declarados.
- Inferencia: cada detección guarda el tamaño del cuadro y el ROI usados (para ubicar sus cajas aunque
  el ROI cambie después). Falta reconstruir el contenedor de inferencia.
- Impresora simulada: cámara estenopeica 3D (piezas con altura, cama que se mueve en Y con el cabezal,
  o `--camera-on-bed`). Las pruebas de `tests/test_bed_map.py` la usan como verdad conocida: con solo
  las 4 esquinas recuperan la focal (±1 %), la posición de la cámara (±1 mm) y ubican un punto sobre
  una pieza de hasta 40 mm de alto, con la cama desplazada, con error menor a 1 mm.

**Pendiente:** API (calibración, foto para calibrar, mapa por trabajo, mapa de calor, geometría en
vivo), pruebas con base de datos, respaldo + migración de la base real, reconstruir backend e
inferencia, pantalla de calibración y vista del mapa (con la Fase 4).

**Decisiones:**
- Una fila por calibración: cada detección se ubica con la calibración vigente cuando se capturó; si
  no había ninguna, con la primera posterior (suponiendo que la cámara no se movió).
- El paralaje se corrige con la altura de la capa (el defecto se supone en la superficie superior).
- En cama móvil, el desplazamiento usa la Y del cabezal de la foto de la capa; como la foto y la
  posición pueden estar hasta ~0,3 s desfasadas, el error estimado crece con la velocidad y la
  ubicación se marca como poco confiable por encima de 20 mm.

## Pendiente con la impresora

Antes de cualquier prueba: VPN HotspotShield desconectada, sesión `wsl -- sleep infinity` abierta y
`curl.exe http://192.168.10.22:7125/printer/info` respondiendo.

1. Fase 0: `backend\.venv\Scripts\python.exe backend\scripts\moonraker_discovery.py` con la impresora
   sin imprimir, y `... --only-ws --ws-seconds 600` durante una impresión.
2. Fase 1: con el backend corriendo, imprimir algo corto y revisar `GET /print-jobs/{id}/telemetry`
   (que lleguen posición, temperaturas y sensores extra), la foto de cada capa y la bitácora
   (`GET /printers/35/events` y `/events/verify`). Confirmar que la Hi tiene `motion_report`; si no, la
   posición sale de `toolhead.position`, que va adelantada al cabezal real.
3. Fase 2: en la bitácora de esa impresión, ver qué origen reciben los cambios del inicio (macros
   propias de Creality); en el log del backend, la línea "Indexed <archivo>" (cuánto tardó el índice) y
   que las macros de la Hi se lean de `configfile`. Para comprobar `console` y `external` hace falta que
   alguien cambie algo durante la impresión (por ejemplo el factor de velocidad desde Fluidd y desde la
   pantalla). Eso ya es una orden a la impresora, así que queda a tu criterio; PrintWatch no lo hace.
