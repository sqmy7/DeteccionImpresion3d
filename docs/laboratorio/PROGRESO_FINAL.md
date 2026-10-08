# Progreso final (prompt maestro, etapas 0 a G)

Reglas: solo lectura sobre las impresoras (GET, WebSocket de lectura, SELECT, lectura de logs); sin `git push`;
commits sin línea de coautoría; las etapas avanzan solo con la confirmación escrita de Samuel; la C y la F
solo con la frase exacta ("autorizo la C", "autorizo la limpieza").

## Estado

| Etapa | Estado |
|---|---|
| 0. Revisión previa | **Hecha** |
| A. Impresora quieta | **en curso**: pasos 1, 2, 3 y 6 hechos; 4 y 5 los hace Samuel; 7 pendiente |
| B. Impresión corta | **preparada**: línea base anotada; falta decidir la pausa automática y que Samuel escriba «inicié» |
| C. Pausa y reanudación | pendiente (necesita "autorizo la C") |
| D. Impresora .21 | pendiente (la .21 no respondía en la Etapa 0) |
| E. Datos del modelo | pendiente (faltan `args.yaml`, `results.csv`, `best.pt`) |
| F. Limpiar historial | pendiente (necesita "autorizo la limpieza" y la pregunta sobre la política del curso) |
| G. Cierre | pendiente |

## Etapa 0: revisión previa (2026-10-08)

- Rama actual `lab-ausente`, árbol limpio. `main` está en `bcf5c18`; la rama trae 10 commits sobre él
  (39 archivos, +1750 −91: estimadores de tiempo restante, guardia de reanudación, cajas al abrir la vista en
  vivo, buscador de cámara de solo lectura, scripts de análisis y reporte, contador de parámetros ONNX,
  redactado de IPv6/MAC, documentación de laboratorio).
- Trabajo 43: `completed` (cerrado 21:58 UTC), cadena de eventos íntegra.
- .22: `print_stats.state = standby`, Klipper `ready`. .21: sin respuesta (HTTP 000).
- Red: SalaSteam_UIS, HotspotShield desconectado.
- Contenedores (backend, inference-worker, postgres, redis): arriba y `healthy`. No hay contenedor `capture`
  (apagado a propósito).

## Etapa A: impresora quieta (2026-10-08)

**1. Unión.** `lab-ausente` unida a `main` con un commit de unión normal (`2ea5f61`, sin reescribir historial).
Backend: 143 pruebas pasan (contra `printwatch_test`). Web: `npm run build` sin errores.

**2. Despliegue del backend.**
- Respaldo de la base real con `pg_dump`: `storage/respaldo_antes_despliegue_2026-10-08.sql` (8,5 MB, 14 tablas,
  no se versiona).
- Reconstruido solo el contenedor `backend` (sin tocar postgres, redis ni el worker). Primer intento: el
  contenedor quedó reiniciándose porque compose se lanzó sin `--env-file .env` y el backend se conectaba
  como `root`; no escribió nada. Se repitió con `docker compose --env-file .env -f infra/docker-compose.yml
  --profile full up -d --no-deps backend` (el mismo modo que usa `start.ps1`) y quedó `healthy`.
- `alembic current` = `e7b3c2a91f04 (head)`, igual a `alembic heads`: no hay migraciones nuevas.
- `/health`: base y Redis `ok`. Listener conectado a la .22 (`state=standby`). El contenedor tiene
  `print_guard.py` y `eta.py`. Cero errores de contraseña ni *tracebacks* en el log tras el segundo arranque.

**3. `capture` reiniciado.** Se corre en Windows con `capture\.venv` (el venv del backend no trae OpenCV) y
`PYTHONPATH=backend`: `python -m capture.main` desde la raíz. Cámara registrada: 36 «C922 Principal», USB
índice 0. Stream continuo a ~6 fps. Redis: `latest_frame_at:36` avanza cada ~3 s (hora actual) y
`latest_frame:36` guarda un JPEG de ~99 KB (1280×720). La web usa esa misma marca para decidir «Sin señal», así
que con esto no debe salir ese aviso. Falta que lo confirmes con tus ojos en la web.
- **Lo que ve la cámara ahora:** está baja y de frente; se ve el lado izquierdo y derecho del pórtico, y de la
  cama solo una franja oscura en el borde inferior (no se ven las cuatro esquinas completas). Esto puede
  dificultar la calibración de las 4 esquinas (ver siguiente paso).

**Acceso a la web.** El login fallaba con «No se pudo iniciar sesión» porque `frontend/.env` (local, ignorado por
git) apuntaba a `192.168.10.100`, una IP vieja de este equipo; ahora es `192.168.10.102`. Se corrigió ese archivo.
A petición de Samuel se restableció la contraseña del usuario administrador `samuel` (un `UPDATE` sobre `users`;
el rol sigue siendo `admin`) y se le entregó la nueva por el chat; no queda guardada en ningún archivo.

**6. Descubrimiento completo con la impresora quieta.** Los 8 pasos terminaron bien (límite de 300 KB/s,
WebSocket de 60 s, solo GET y suscripción). Comparación completa en
`docs/laboratorio/COMPARACION_QUIETA_IMPRIMIENDO.md`. Lo esencial:
- Objetos, configuración, macros, `printer_info`, `server_info` y `webcams` son **idénticos** a lo medido
  imprimiendo (117 objetos, 71 macros). Webcams: lista vacía, ninguna URL probada.
- WebSocket: mismo ritmo (un mensaje cada 0,25 s); 2.432 B/s quieta contra 4.165 B/s imprimiendo (se suscribió
  a 116 y a 45 objetos, así que no es comparable 1 a 1).
- 54 campos solo se mueven imprimiendo (posición real, ventilador, `gcode_move`, `virtual_sdcard`...).
- Ningún log descargado (128 MB, no se versionan) contiene `out of range`.

**7. Revisión visual con datos reales: pendiente.** Para tomar capturas con el navegador de pruebas había que
pasar la contraseña de `samuel` como argumento de línea de comandos y el sistema de permisos no lo dejó; no se
buscó otro camino. Opciones: que Samuel revise la web a mano y diga qué ve, o que autorice un usuario temporal
de solo lectura como en la fase anterior.

**Hallazgo en la calibración (2026-10-08, Samuel).** Al guardar la calibración la web respondía 422 y las
esquinas de la lista salían en «(0, 0)» aunque se arrastraran los puntos. Causa (error mío de la fase anterior):
el tamaño de la cama se calculaba como `mesh_min + mesh_max` de la malla, y con la impresora quieta y sin malla
cargada Klipper reporta `[0, 0]` a `[0, 0]` (con la malla `default` cargada, imprimiendo, da 10 + 250 = 260, y por
eso en el trabajo 43 no se vio). Con tamaño 0 las cuatro esquinas de la cama eran el mismo punto y el backend lo
rechazaba. Corregido en `bedSize` (web) y `bed_dimensions` (backend): una malla vacía no cuenta y se usa 260 mm;
la capa y la leyenda de la malla no se dibujan si está vacía; el 422 ahora dice qué falló (esquinas de cama o
marcas cruzadas). Pruebas: una para `bed_dimensions` con la geometría real en reposo, una para el mensaje.
Backend 144 pruebas pasan.

## Aviso de pausa de la .22 (2026-10-08, 18:22 hora de Colombia = 23:22 UTC)

Samuel avisó que había pausado una impresión de la .22. **No se confirmó**: al comprobarlo, la impresora estaba
en `standby` (`print_stats.state`), sin archivo cargado, `pause_resume.is_paused = false`, y dos lecturas
seguidas dieron lo mismo. Tampoco hay trabajo nuevo: el último en la base es el 43 (`completed`) y el último del
historial de Moonraker es el 86 (el mismo). No se inventó ninguna pausa y no se descargaron los logs del tramo
(ver abajo).

- **Lo que sí registró la bitácora** (solo lectura, `printer_events`): entre 23:18:35 y 23:20:33 UTC hubo una
  operación con filamento sin trabajo en marcha: boquilla 0 → 120 → 250 °C y cama a 80 °C (origen `external`,
  es decir, no se pudo atribuir a la consola, a un archivo ni a PrintWatch), cambios en los sensores de
  filamento 3, 4 y 5 de la caja (origen `printer`) y a las 23:20:33 los dos objetivos volvieron a 0. Hora de
  Colombia: 18:18 a 18:20. Ningún evento de pausa, error ni cancelación. Posiciones al comprobar: cabezal en Z 60,2 mm.
- **Cadena de eventos:** íntegra, 38 eventos verificados (`verify_chain`), sin eslabón roto.
- **`capture`:** corre (cuadros de la C922 llegan a Redis, `latest_frame_at` con la hora actual). Por lo tanto la
  **pausa automática está activa**: pausa tras 3 capas seguidas de *spaghetti* con 15 s de gracia que se pueden
  abortar en la web. No dispara hoy porque no hay trabajo en curso. No se arrancó ni se detuvo nada.
- **Calibración de la C922:** guardada el 22:56 UTC (id 1, cámara 36). Cama móvil, Y de referencia 130 mm,
  imagen 1280×720, esquinas de la cama (0,0), (260,0), (260,260), (0,260). **Valores a vigilar:** focal estimada
  1.490 px, 1,6 veces la típica de la C922 con 78° (≈ 907 px), señal de que las marcas no coinciden bien con las
  esquinas reales o que alguna se marcó sobre una zona no visible; cámara estimada a ~10,5 cm de altura,
  27 cm delante del borde frontal y 5,7 cm a la izquierda del origen de X. Altura y distancia son plausibles
  para una cámara baja y de frente (como se ve en el cuadro), pero con esa focal el error de ubicación será
  mayor que el estimado. La web no mostró aviso porque la focal se estimó (no se supuso).
- **Pendiente (descubrimiento completo y logs):** no se corrió nada pesado contra Moonraker. El descubrimiento
  completo y la descarga de `klippy.log`/`moonraker.log` del tramo de la pausa esperan: lo primero, a `standby`;
  lo segundo, a que haya una pausa real que acotar (5 minutos antes de la hora exacta).

## Recalibración de la C922 (2026-10-08, 18:26 hora de Colombia = 23:26 UTC)

Solo lectura (`SELECT`, `GET` de la posición, y una imagen del cuadro actual con las marcas dibujadas encima).

| | Calibración 1 (22:56 UTC) | Calibración 2 (23:26 UTC) |
|---|---|---|
| Y de referencia | 130 mm | **260 mm** |
| Focal estimada | 1.490,1 px | **1.498,6 px** |
| Cámara, altura | 10,5 cm | 11,1 cm |
| Cámara, distancia al borde frontal | 27,2 cm delante | 26,1 cm delante |
| Cámara, X | −5,8 cm | −4,4 cm |
| Marcas en la imagen (px, de 1280×720) | (184,433) (1156,277) (696,126) (30,177) | **(215,479) (1231,307) (696,136) (8,195)** |

(Calibración 2, puntos normalizados: [0,1682; 0,6654], [0,9619; 0,4260], [0,5435; 0,1888], [0,0060; 0,2702].
Orden: frente izquierda, frente derecha, fondo derecha, fondo izquierda; esquinas de la cama
(0,0), (260,0), (260,260), (0,260) mm.)

- **La focal NO se acerca a ~907 px: sigue en ~1.500 px (1,65 veces la típica).** Cambió 0,6 % entre las dos
  calibraciones aunque la cama estaba en otra Y y las marcas se pusieron de nuevo, así que la estimación es
  estable. Posición de la cámara casi igual (altura 10,5 a 11,1 cm, 26 a 27 cm delante).
- **Las marcas están bien puestas.** Dibujadas sobre el cuadro actual caen sobre las cuatro esquinas visibles
  de la placa (la cámara ya no está donde estaba a las 17:26: ahora ve la placa completa desde el frente
  izquierdo y abajo). Por eso no es un error de clic.
- **Con una focal fija de 907 px las marcas no cuadran** (calibración 2, error de reproyección por marca,
  1 a 4): 3,8 / 18,3 / **63,5** / 39,8 mm sobre la cama (8,6 / 18,7 / 45,2 / 31,9 px); la 3 (fondo derecha) es
  la que más se aleja. Con la focal estimada el error es de 0,6 a 5,9 mm: el modelo de cámara con ~1.500 px
  explica bien las cuatro marcas; con 907 px no. Las cifras vienen de ajustar la pose por mínimos cuadrados
  con el código nuevo (aún sin desplegar).
- **Posibles causas, sin verificar** (que sean ~1.500 px no significa que el lente lo sea): (1) la cámara no
  trabaja con su campo completo de 78° en este modo (recorte o zoom digital de la cámara o de Windows);
  (2) la placa que se marcó no mide exactamente 260 × 260 mm (la placa se ve más grande que el área
  imprimible); (3) distorsión del lente, que este modelo ignora; (4) una vista casi rasante, en la que la
  focal se estima mal con cuatro puntos. Una forma de separarlas: medir la placa con una regla, y comparar
  con un objeto de tamaño conocido en el cuadro.
- **Lo que importa para ubicar defectos** (el mapa de la cama) es la transformación imagen → cama, que no
  depende de la focal. La focal solo afecta a la posición de la cámara y, con ella, a la corrección de
  paralaje de las piezas altas.
- **Y de la cama:** al tomar la foto de la calibración 2 la web guardó Y = 260 mm (la última lectura en vivo
  en ese momento; la 1 guardó 130 mm: la cama estaba a mitad de recorrido). Ahora, tres lecturas de
  `motion_report.live_position` dan Y = 260,0 mm, y `toolhead.position` también. **Coinciden: no hay señal de
  que la cama se moviera entre la foto y el guardado.** Límite: no se puede ver lo que pasó en el intervalo
  (en `standby` no se guarda telemetría y la bitácora no registra posiciones), pero tampoco hubo ningún evento
  de la bitácora desde las 23:20:33 UTC y el estado seguía en `standby`. La Y distinta entre las dos
  calibraciones (130 y 260) la compensa `reference_y`.

## Focal fija y error de reproyección en la calibración (2026-10-08)

Pedido de Samuel: poder fijar la focal conocida en vez de estimarla, ver el error de reproyección de las
cuatro marcas y recibir un aviso si una marca queda muy lejos de su esquina.

- **Focal fija:** `focal_px` opcional al guardar (`POST /cameras/{id}/calibration`); en la web, «Focal de la
  cámara»: *Estimarla*, *C922 (907 px a esta resolución)* u *Otro valor*. Se rechaza lo implausible
  (menos de 0,2 o más de 5 veces la diagonal de la imagen). Con focal fija solo se calcula la posición de la
  cámara.
- **Error de reproyección:** la homografía de cuatro puntos ajusta las marcas exactamente (error 0 por
  construcción), así que el error se mide con el modelo de cámara: con la focal en uso se ajusta la pose
  (rotación y traslación) por mínimos cuadrados sobre las cuatro marcas y se compara cada esquina
  reproyectada con su marca, en píxeles y en milímetros sobre la cama. La marca con más error es la
  sospechosa. (Un primer intento que no ajustaba la pose dejaba siempre la marca 1 en 0 y repartía mal la
  culpa; se descartó.) Se calcula al leer, a partir de lo ya guardado: **sin migración**.
- **Avisos** (códigos que explica la web): `focal_unusual` (focal estimada a más de 25 % de la típica),
  `focal_fixed`, `mark_far_from_corner` (error mayor que 4,5 % de la cama, unos 12 mm: tres veces el error
  típico de un clic) y `mark_far_at_typical_focal` (con la focal de la C922 una marca no encajaría, aunque la
  focal en uso sea otra). La lista de calibraciones ahora también trae los avisos (antes solo la respuesta
  al guardar) y la tabla de errores de la focal en uso y de la focal conocida.
- **Se conserva la focal fija al ubicar defectos:** `calibration_from_row` vuelve a fijarla si la guardada
  difiere en más de 1 px de la que dan las marcas solas. Límite: una focal fija igual (±1 px) a la estimada
  se muestra como «estimada»; no cambia ningún cálculo.
- **Con las marcas reales de hoy** (calibración 2): focal estimada 1.499 px (aviso `focal_unusual`, errores
  de 0,6 a 5,9 mm); con 907 px fijos, errores de 3,8 / 18,3 / 63,5 / 39,8 mm y `mark_far_from_corner`; la
  marca 3 (fondo derecha) es la más lejana. Hay una prueba con esas marcas.
- No hay vista previa del error antes de guardar: se ve al guardar, y recalibrar crea otra fila (la vigente es
  la última; las anteriores quedan en el historial).
- Pruebas: 21 de matemática de la cama, 2 de la API; suite completa 149 pasan.

## Etapa B: preparación (2026-10-08, 18:40 hora de Colombia = 23:40 UTC)

**1. Pausa automática: no existe interruptor ni modo «solo aviso». No se cambió nada; se espera la decisión de
Samuel.** Qué hace (`backend/app/services/auto_pause.py`, disparada desde `ws/redis_listener.py` con cada
detección): cuando las **3 últimas capas** de un trabajo traen *spaghetti*, anuncia por la web («auto_pause.pending»)
y arranca una cuenta de 15 s; **al vencer, PrintWatch mismo manda `pause` a Moonraker** (`send_print_action`), salvo
que alguien la aborte en la web (el aviso solo se ve con la web abierta). No hay ajuste de configuración; el único
modo de evitarla es que no haya detecciones o cambiar el código.

Riesgo para esta prueba: el modelo nunca se evaluó con imágenes de la C922 con la Hi (solo con fotos de Roboflow);
si da 3 falsos *spaghetti* seguidos en una impresión corta, PrintWatch pausa solo, y la reanudación de Creality es
justo la secuencia que acabó en el incidente del 25-09 (nunca se validó). Además, con la pausa ejecutada, la prueba
de la Etapa B se convierte en la de la Etapa C sin la autorización de esa etapa.

Opciones (ninguna aplicada):
- **A. Añadir un ajuste `AUTO_PAUSE_MODE` (`on` por defecto, `warn`, `off`)** en `auto_pause.py` y la configuración;
  en `warn` solo se anuncia y se registra, sin enviar la pausa. Hay que reconstruir el contenedor del backend
  **antes** de iniciar la impresión. Revertir: quitar la variable del `.env` y reconstruir (o `git revert` del commit).
  Es la que se recomienda: conserva toda la observación de la Etapa B.
- **B. Parar el contenedor `inference-worker`** durante la prueba (sin detecciones no hay racha). Revertir:
  `docker start infra-inference-worker-1`. Pierde justo lo que se quiere observar (detección por capa).
- **C. Dejarla como está** con la web abierta en «En vivo» y Samuel listo para abortar la cuenta de 15 s. Yo no puedo
  abortar nada.

**2. Estado verificado (solo lectura):**
- Red: SalaSteam_UIS, HotspotShield desconectado. .22 responde; .21 sin respuesta (HTTP 000).
- Contenedores: backend (reconstruido 23:35 UTC), inference-worker, postgres y redis, todos `healthy`. Alembic en
  `e7b3c2a91f04` (head).
- Listener conectado a la .22 (23:35:31 UTC), línea base `state=standby layer=0/0 z=60.20`.
- `capture` corre (procesos de `capture.main` vivos); `latest_frame_at:36` = hora actual al leerlo (cuadros
  frescos de la C922).
- CPU base (reposo): backend 0,2 %, worker 0,0 %, postgres 0,0 %, redis 0,5 %; equipo 18 %; 4 núcleos en WSL.
  El worker usa 1 hilo para ONNX.

**3. Línea base de la .22 a las 23:40 UTC:**
- `print_stats.state` = `standby`, sin archivo, `idle_timeout` = Ready.
- Posición del cabezal/cama (`motion_report.live_position`): X 0,0, **Y 260,0**, Z 60,2 mm (igual en
  `toolhead.position`); ejes sin referenciar (`homed_axes` vacío).
- Boquilla 34,7 °C (objetivo 0), cama 32,6 °C (objetivo 0). `speed_factor` 1,0, `extrude_factor` 1,0.
- Calibración vigente de la C922: la 2 (Y de referencia 260 mm, focal 1.499 px estimada, avisos `focal_unusual`
  y `mark_far_at_typical_focal`); no se tocó.
- Último trabajo: 43 (`completed`). El siguiente número esperado en la base: el próximo `print_jobs.id` (>43).

## Etapa B: pausa automática en modo aviso (2026-10-08, 18:47 hora de Colombia = 23:47 UTC)

Samuel eligió la opción A. Se añadió `AUTO_PAUSE_MODE` (`on` por defecto, `warn`, `off`):

- **`on`**: sin cambios (aviso, cuenta de 15 s, `pause` a Moonraker).
- **`warn`**: al cerrarse la racha de 3 capas con *spaghetti* no hay cuenta ni pausa; se registra el evento
  `auto_pause.would_pause` en la bitácora (origen `monitor`, `print_job_id`, hora, `detail` con `layer`,
  `confidence`, `streak` de las tres capas, `sent: false`) y se anuncia en la web con un banner «Modo aviso».
  Para contar cuántas veces habría pausado: `SELECT count(*) FROM printer_events WHERE event_type =
  'auto_pause.would_pause';`.
- **`off`**: no hace nada (ni aviso ni evento ni pausa).
- Un valor inválido (por ejemplo `maybe`) impide arrancar el backend, en vez de pausar o no pausar en silencio.
  Se acepta con mayúsculas y espacios.
- Segunda guarda: `_execute` no envía nada si el modo no es `on`.
- Código: `backend/app/core/config.py`, `backend/app/services/auto_pause.py`; web: banner en
  `AutoPauseOverlay.tsx`, etiqueta en `events.ts`, filtro de estados de la bitácora. `.env.example` documenta la
  variable.
- **Pruebas** (`backend/tests/test_auto_pause_modes.py`, contra la impresora simulada, que cambia de estado de
  verdad): `on` → la simulada queda `paused` con 1 pause recibido; `warn` → sigue `printing`, 0 pause, un evento
  con capa 9 y confianza 0,92 y la cadena íntegra; `off` → 0 pause y ningún evento; por defecto `on` y un
  valor erróneo falla. Suite completa: **153 pasan**.

**Despliegue.** Respaldo previo con `pg_dump`: `storage/respaldo_antes_modo_aviso_2026-10-08.sql` (8,5 MB, no se
versiona). `AUTO_PAUSE_MODE=warn` añadido al final del `.env` real (no se versiona) con un comentario. Solo se
reconstruyó el contenedor `backend`, con la .22 en `standby`. Comprobado: contenedor `healthy`, el modo dentro
del contenedor es `warn`, `alembic current` = `e7b3c2a91f04` (head, sin migraciones), `/health` base y Redis `ok`,
listener conectado a la .22 (`standby`, `layer=0/0`), `capture` con cuadros frescos, SalaSteam_UIS.

**Cómo revertir** (volver a `on`): borrar las dos últimas líneas del `.env` (el comentario y
`AUTO_PAUSE_MODE=warn`) y reconstruir solo el backend, con el mismo comando que se usa siempre:
`docker compose --env-file .env -f infra/docker-compose.yml --profile full up -d --build --no-deps backend`
(en WSL, desde la raíz del repositorio). Sin la variable el modo es `on`. Se hace **cuando no haya impresión en
curso**. Para comprobarlo: `docker exec infra-backend-1 python -c "from app.core.config import settings;
print(settings.auto_pause_mode)"` debe imprimir `on`.

**Estado al cerrar el despliegue:** modo **warn**; la .22 en `standby`, sin archivo, cama en Y 260,0 mm; nada se
envió a ninguna impresora. Se espera el «inicié» de Samuel.

## Pendiente para después de la Etapa B: dos detalles del Panel general (diagnóstico, sin cambios en el código)

Pedido de Samuel (2026-10-08). Se revisó solo leyendo código y datos; no se tocó nada ni se corrieron pruebas
(gastan CPU y falsearían la medición de la Etapa B). Se corrige y se prueba **cuando termine la Etapa B**.

**(2) «Capa 0 / 486 · 2 h 45 min» en la tarjeta del trabajo 43** (`frontend/src/pages/OverviewPage.tsx`, 42 y 83).
Los dos datos salen mal por motivos distintos:
- **Capa 0:** `layer = live?.layer_number ?? summary.data?.current_layer`. `live` es la última lectura en vivo de la
  impresora (menos de 10 s) y, quieta, reporta `layer_number = 0`; como `0` no es `null`, el `??` no cae al
  dato del trabajo. Se muestra la capa de la impresora ahora, no la del trabajo mostrado. El trabajo 43 sí tiene
  su propia capa final: `layers` guarda de la 275 a la 486 (210 filas, PrintWatch se unió a mitad) y
  `get_job_summary` devuelve `current_layer = 486`. Arreglo: usar la lectura en vivo solo si el trabajo mostrado
  está en curso (`running`); si no, la capa del trabajo.
- **2 h 45 min:** es `secondsBetween(started_at, ended_at)`, o sea el tiempo que PrintWatch siguió el trabajo
  (19:13 a 21:58 UTC, desde el 45 %). La impresión real duró ~6 h 01 min: el reloj de la impresora
  (`print_stats.print_duration`, 21.660 s) ya se guarda en `telemetry_samples.extra` y el reporte PDF lo usa
  (`report.py`), pero el resumen del trabajo no lo expone. Arreglo: añadir al resumen la duración de impresión
  del reloj de la impresora (último valor de `extra`) y si PrintWatch se unió tarde; mostrar la real, con una nota
  «PrintWatch lo siguió 2 h 45 min». Mismo error en `JobsListPage.tsx` (41 y 76) y `LivePrintPage.tsx` (52):
  se revisan juntos. Los trabajos anteriores a 2026-10-08 no tienen ese dato; para ellos se queda la duración
  seguida, sin afirmar más.

**(1) Miniatura de video negra en la tarjeta de la impresora.** Sin causa confirmada. Lo que se descartó leyendo:
la tarjeta usa el mismo componente (`VideoFeed`) y el mismo endpoint (`/cameras/{id}/stream`) que «En vivo», y la
cámara elegida es la misma (id 36); el backend no reporta errores de conexiones a la base ni de Redis; el servidor
muestra un solo `GET .../stream` desde el último despliegue. Hipótesis a probar con un navegador: (a) la altura del
`<img class="h-full w-full object-cover">` dentro de un contenedor `aspect-video` sin altura propia (se pinta a
0 de alto hasta el primer cuadro y puede quedarse así); (b) conexiones de flujo que se acumulan al pasar de «En
vivo» al Panel (un navegador abre pocas conexiones por servidor y el flujo es una conexión que no termina);
(c) el cuadro de relleno de «sin señal» si en ese momento `capture` estaba apagado. Plan: reproducirlo con el
entorno de demostración y un navegador (sin usar la cuenta real), medir el tamaño real de la imagen y los
`GET .../stream` abiertos, corregir lo que salga y dejar una prueba.

## La C922 no está conectada: el video sale negro (2026-10-08, ~18:55 hora de Colombia = 23:55 UTC)

Samuel mandó una captura de «En vivo» con el video negro. Comprobado (solo lectura):
- El último cuadro en Redis es fresco (`latest_frame_at` avanza cada ~2 s) pero **completamente negro**: media 0,
  máximo 0, 1280×720, JPEG de 15 KB (un cuadro real pesa ~100 KB). A las 23:28 UTC aún era una imagen real de la
  C922 (se dibujaron las marcas de la calibración 2 sobre ella).
- Windows: la **C922 (Logitech) figura como no presente** (`Present = False`, tres entradas «C922 Pro Stream
  Webcam» y su micrófono). La única cámara presente es una «USB Camera» genérica (VID 5258, PID 4A55), más una
  «Integrated Camera» en estado de error. `capture` abre la cámara por **índice 0** (`source_uri = 0`), y ahora el
  índice 0 es esa otra cámara, que entrega negro. El registro de `capture` muestra dos fallos de lectura
  («Failed to read frame from USB camera '0'») con reapertura automática.
- La causa probable es que la C922 se desconectó del USB (cable o puerto) después de moverla para la calibración;
  no se verificó físicamente.
- **Efecto sobre la Etapa B:** la comprobación «cuadros frescos» de la línea base midió solo la hora, no el contenido,
  y ya no vale: con esta cámara no habría fotos útiles por capa ni detecciones reales. Hay que reconectar la C922
  y reiniciar `capture` (hoy tiene abierta la cámara equivocada) antes de iniciar la impresión.
- **Mejoras propuestas (no hechas):** que `capture` trate un cuadro todo negro como «sin señal» (hoy la web lo
  muestra como video vivo porque el cuadro es reciente) y que identifique la cámara por nombre o identificador en
  vez de por índice (el índice cambia al desconectar o conectar otra cámara).
