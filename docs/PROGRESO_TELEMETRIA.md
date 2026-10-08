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
| 2. Bitácora de intervenciones | Terminada y desplegada (pantalla en la Fase 4); falta verla con una impresión real |
| 3. Mapa de la cama | Terminada y desplegada (pantalla en la Fase 4); falta calibrar la cámara real |
| 4. Rediseño de la web | Terminada; probada con la impresora simulada (modo demostración) |
| 5. Innovación | En curso: puntaje combinado y salud hechos; faltan el reporte PDF y el costo |

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

## Fase 3: mapa de la cama

**Hecho:**
- `app/services/bed_map.py`: homografía imagen-cama a partir de 4 puntos (lo mismo que
  `cv2.findHomography` con cuatro puntos, en Python puro), estimación de la focal y la posición de la
  cámara desde esa homografía (restricciones de Zhang con una vista), corrección de paralaje con la
  altura de la capa y desplazamiento en Y de la cama (la Creality Hi es de cama móvil), con una
  estimación del error de cada ubicación.
- `app/services/defect_map.py`: ubica cada caja de defecto de un trabajo con la calibración vigente
  al capturar, la foto de telemetría de la capa y los objetos del archivo; mapa de calor por celdas.
- Migración `d4e8b2c61f05` (a mano): tabla `camera_calibrations` y columna `print_jobs.geometry`.
  Probada en `printwatch_test` (subir, `alembic check`, bajar, subir) y aplicada a la base real el
  2026-10-08, después de respaldarla en `storage/respaldo_antes_mapa_cama_2026-10-08.sql`.
- Listener: guarda en el trabajo los límites de los ejes, la malla de la cama y los objetos declarados.
- Inferencia: cada detección guarda el tamaño del cuadro y el ROI usados (para ubicar sus cajas aunque
  el ROI cambie después). Falta reconstruir el contenedor de inferencia.
- Impresora simulada: cámara estenopeica 3D (piezas con altura, cama que se mueve en Y con el cabezal,
  o `--camera-on-bed`). Las pruebas de `tests/test_bed_map.py` la usan como verdad conocida: con solo
  las 4 esquinas recuperan la focal (±1 %), la posición de la cámara (±1 mm) y ubican un punto sobre
  una pieza de hasta 40 mm de alto, con la cama desplazada, con error menor a 1 mm.

- API: `POST/GET /cameras/{id}/calibration`, `GET /cameras/{id}/calibrations`,
  `GET /cameras/{id}/snapshot` (con la antigüedad del cuadro en `X-Frame-Age-Seconds`),
  `GET /print-jobs/{id}/bed-map`, `GET /printers/{id}/bed-heatmap`, `GET /printers/{id}/geometry`.
  Calibrar solo lee el estado de la impresora (su Y y el tamaño de la cama); no le manda nada.
- `capture` guarda la hora de cada cuadro junto a la imagen (`latest_frame_at:{camara}`).
- Prueba de la API contra la base de pruebas: calibra con las esquinas que ve la cámara simulada, ubica
  un defecto sobre una pieza con la cama quieta (error < 1,5 mm, confiable, objeto correcto) y otro con
  la cama a 250 mm/s (no confiable); el mapa de calor cuenta solo el confiable. 94 pruebas en total.
- Desplegado (backend e inferencia reconstruidos). Con los datos reales, sin calibración, los 15
  recuadros de defectos de los trabajos 34 y 35 se informan como no ubicables.
- De paso: el listener deja una sola línea de aviso por reintento cuando la impresora no responde (antes
  una traza completa cada 10 s), y se silenciaron dos avisos de Pydantic del arranque.

**Pendiente:** calibrar la C922 en el laboratorio (la pantalla de calibración y la vista del mapa se
hicieron en la Fase 4).

**Decisiones:**
- Una fila por calibración: cada detección se ubica con la calibración vigente cuando se capturó; si
  no había ninguna, con la primera posterior (suponiendo que la cámara no se movió).
- El paralaje se corrige con la altura de la capa (el defecto se supone en la superficie superior).
- En cama móvil, el desplazamiento usa la Y del cabezal de la foto de la capa; como la foto y la
  posición pueden estar hasta ~0,3 s desfasadas, el error estimado crece con la velocidad y la
  ubicación se marca como poco confiable por encima de 20 mm.

## Fase 4: rediseño de la web

**Hecho:**
- Sistema de diseño: colores como variables CSS (`frontend/src/index.css`) usados por Tailwind,
  tema oscuro, paleta Okabe-Ito (distinguible con daltonismo) y cada clase de defecto con un código
  de dos letras además del color (`config/defectClasses.ts`). Componentes base en
  `components/ui/` (botón, tarjeta, insignia, indicador, pestañas, tabla, estados de carga, vacío y
  error). Íconos de `lucide-react`; gráficas con Recharts. Fechas y horas en hora de Colombia
  (`lib/format.ts`).
- Estructura: menú lateral en pantallas anchas y menú desplegable en el celular; cada impresora con
  pestañas En vivo, Trabajos, Bitácora y Cámara y cama.
- Pantallas:
  - **Panel general:** totales, tarjeta por impresora con foto, progreso y temperaturas, y la
    actividad reciente de la bitácora.
  - **Impresión en vivo:** video, progreso con tiempo restante, lecturas (temperaturas, velocidad,
    flujo, ventilador, desfase de Z, sensores extra), gráficas de telemetría con marcas de eventos y
    capas con defecto, mapa de la cama (piezas, recorrido del cabezal, defectos con su error), tira de
    capas con la foto y el análisis de cada una, bitácora y alertas del trabajo.
  - **Historial y repetición:** lista de trabajos; repetición a ×10, ×60 o ×300 en la que todo (capa,
    foto, cama, lecturas, bitácora) muestra ese instante; clic en la gráfica para saltar; exportar las
    capas en CSV; `?capa=N` abre la repetición en esa capa (lo usan las alertas).
  - **Bitácora:** filtros por tipo y por origen, por trabajo, verificación de la cadena de hashes y
    explicación de cada origen.
  - **Cámara y cama:** calibración marcando las cuatro esquinas sobre la foto (avisa si el cuadro es
    viejo o si la cama se movía), historial de calibraciones y mapa de calor de defectos con o sin la
    malla.
  - **Analítica:** trabajos, tasa de éxito, horas, capas con defecto, intervenciones y filamento;
    defectos por clase, resultados, intervenciones por origen, defectos por trabajo, estabilidad de la
    boquilla y tabla de trabajos; por impresora y por período.
  - **Alertas:** centro con filtros por estado; cada alerta dice el trabajo, el archivo y la capa, con
    enlace a la repetición en esa capa.
  - Los avisos de pausa automática (pendiente con cuenta regresiva, ejecutada, fallida) pasaron al
    sistema de diseño sin cambiar su lógica.
- Backend para estas pantallas: `GET /analytics/summary`; la lista de alertas incluye trabajo, capa y
  archivo; la foto de cada capa guarda la velocidad en Y medida (`velocity_y`, para el error del mapa
  en cama móvil); un trabajo que el listener encuentra terminado al conectarse se cierra con la hora de
  su última capa (antes quedaba con la hora de la reconexión: así salió el trabajo 34 con 94 h).
- **Modo demostración** (`backend/scripts/demo_environment.py`, explicado en el README): base
  `printwatch_demo`, impresora simulada, backend en el puerto 8010 aislado del real (Redis en la base
  2, canales con prefijo `demo:` gracias a `REDIS_CHANNEL_PREFIX`, fotos en
  `storage/demo_snapshots/`) y detecciones sintéticas marcadas como tales. El guion cubre
  intervenciones, una cancelación, la alerta de atasco y una pausa automática con reanudación desde
  la consola; `--live` deja una sola impresión en curso.
- Capturas en escritorio y celular en `docs/capturas/` (17), tomadas con Playwright y Edge sobre el
  modo demostración.
- Pruebas: 97 (nueva: la lista de alertas con su trabajo y capa). `npm run build` sin errores.

**Mediciones del frontend (compilado):** carga inicial 236 KB (74 KB comprimido); Recharts y las
gráficas van en un bloque aparte de 386 KB (107 KB comprimido) que solo se descarga al abrir una
página con gráficas. Las series largas llegan ya reducidas por el servidor (1.500 puntos como máximo
en la repetición).

**Decisiones:**
- Solo tema oscuro: es el que se usa junto al video de la cámara. Al estar todo en variables, un tema
  claro sería otra lista de valores.
- Fuentes del sistema, no fuentes web: la red del laboratorio puede no tener internet.
- Las marcas de tiempo de las gráficas se calculan en horas redondas (cada 15 s, 1 min, 5 min...)
  según el ancho disponible; las automáticas de Recharts caían en segundos sueltos y a veces se
  superponían.
- La telemetría en vivo se guarda en un almacén propio (`lib/telemetryStore.ts`) fuera del estado de
  React; solo se redibujan los componentes que la leen.
- El mapa de la cama dibuja los defectos poco confiables como un círculo punteado del tamaño de su
  error, en vez de esconderlos; el mapa de calor no los cuenta.
- La demostración nunca usa la base, el Redis ni las fotos del sistema real, y sus detecciones son
  sintéticas: sirve para mostrar la interfaz y el flujo, no mide el modelo.

**Pendiente:** ver la web con la impresora real (video de la C922, telemetría real, mapa con la
calibración real) y desde el celular en la red del laboratorio.

## Fase 5: innovación

**Hecho:**
1. **Puntaje combinado de modelo y telemetría** (`app/services/fusion.py`,
   `GET /print-jobs/{id}/fusion`). Para cada recuadro de defecto se miran las muestras de la capa
   recién impresa (la que se ve arriba en la foto) y se revisan las señales que explican esa clase:
   sub-extrusión (sin filamento, calentador al máximo, boquilla fría, flujo bajado, más rápido de lo
   laminado), exceso de material (flujo subido, boquilla caliente), stringing (boquilla caliente o
   subida respecto de la primera capa), warping (cama fría o bajada) y desplazamiento de capa
   (velocidad subida). Puntaje = 1 − (1 − confianza) × ∏(1 − peso de cada señal cumplida). La web lo
   muestra junto a cada detección ("modelo 58 % · combinado 71 %") con las señales a favor y la
   explicación completa plegada. No toca las alertas ni la pausa automática.
2. **Salud de la impresora** (`app/services/health.py`, `GET /printers/{id}/health`, pestaña
   "Salud"). Por trabajo y calentador: potencia para mantener la temperatura, oscilación y mayor
   desviación una vez asentada, y velocidad de calentamiento desde frío. Cada trabajo se compara
   con la línea base de la misma impresora en una carta de control.
- Nota "Estimación · cómo se calcula" (componente `EstimateNote`) en todo dato derivado: posición en
  la cama (vivo, repetición, cámara y cama, analítica), puntaje combinado y salud.
- Impresora simulada: `/mock/heater` (potencia para mantener, constante de tiempo y temperatura
  actual de cada calentador). Modo demostración: el guion pone una causa en la telemetría antes de
  cada defecto (boquilla subida, cama bajada desde la pantalla, flujo bajado) y `--health` hace 8
  impresiones cortas con desgaste simulado en las dos últimas. La demo ya no calienta al instante.
- Pruebas: 113.

**Decisiones:**
- Combinación tipo "noisy-OR": cada señal es una causa independiente que puede explicar el defecto.
  Es simple de explicar, nunca baja la confianza del modelo y nunca llega a 100 %.
- Umbrales con respaldo: ±5 °C (banda que Klipper considera en rango, `hysteresis` de
  `verify_heater`), 5 % de flujo (paso de la calibración de flujo de los laminadores), 95 % de PWM
  (sin margen para sostener la temperatura). Los pesos (0,6 / 0,3 / 0,15) son iniciales y la web lo
  dice.
- Salud: "asentado" = a menos de 1 °C del objetivo, el criterio de Klipper (`PID_SETTLE_DELTA`) para
  dar por terminada la espera de M109. Se compara a igual objetivo (pasos de 5 °C). Línea base: los
  primeros 5 a 10 trabajos, dejando fuera los 3 últimos cuando hay suficientes. Reglas: ±3σ
  (Shewhart), 2 de 3 más allá de 2σ y 8 seguidos del lado malo (Western Electric). Aparte, una
  desviación de más de 5 °C ya asentada se marca siempre.
- Los resultados de salud de los trabajos terminados quedan en memoria del backend; los del
  puntaje se calculan en cada consulta (13-33 ms por trabajo en la demo).

**Pendiente:** 3. reporte PDF por trabajo; 4. estimación de costo (filamento y energía).

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
4. Fase 3: reiniciar `capture` (para que guarde la hora de cada cuadro) y calibrar la C922 desde la web
   con la impresora quieta (sin imprimir): marcar las cuatro esquinas de la cama e indicar si la cámara
   está fija (la cama se mueve en la imagen) o va sobre la cama. Revisar que la posición de cámara
   estimada sea razonable (altura y distancia aproximadas a la real) y, en la siguiente impresión con
   detecciones, que los defectos caigan sobre la pieza en el mapa.
5. Fase 4: durante esa impresión, recorrer las pantallas en el computador y en el celular (misma red):
   video en vivo, lecturas que cambian cada segundo, marcas de la bitácora en las gráficas, tira de
   capas con fotos y, al terminar, la repetición y la analítica del trabajo.
