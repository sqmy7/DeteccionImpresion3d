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
| 2. Bitácora de intervenciones | Sin empezar |
| 3. Mapa de la cama | Sin empezar |
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

## Pendiente con la impresora

Antes de cualquier prueba: VPN HotspotShield desconectada, sesión `wsl -- sleep infinity` abierta y
`curl.exe http://192.168.10.22:7125/printer/info` respondiendo.

1. Fase 0: `backend\.venv\Scripts\python.exe backend\scripts\moonraker_discovery.py` con la impresora
   sin imprimir, y `... --only-ws --ws-seconds 600` durante una impresión.
2. Fase 1: con el backend corriendo, imprimir algo corto y revisar `GET /print-jobs/{id}/telemetry`
   (que lleguen posición, temperaturas y sensores extra), la foto de cada capa y la bitácora
   (`GET /printers/35/events` y `/events/verify`). Confirmar que la Hi tiene `motion_report`; si no, la
   posición sale de `toolhead.position`, que va adelantada al cabezal real.
