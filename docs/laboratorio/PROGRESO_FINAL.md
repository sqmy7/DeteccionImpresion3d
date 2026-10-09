# Progreso final (prompt maestro, etapas 0 a G)

Reglas: solo lectura sobre las impresoras (GET, WebSocket de lectura, SELECT, lectura de logs); sin `git push`;
commits sin línea de coautoría; las etapas avanzan solo con la confirmación escrita de Samuel; la C y la F
solo con la frase exacta ("autorizo la C", "autorizo la limpieza").

> **Aclaración (Samuel, 2026-10-09):** las pruebas del 2026-10-08 se hicieron con una cámara USB genérica provisional,
> no con la Logitech C922, que será la cámara de la implementación final. Donde este registro dice «C922» al hablar
> de lo medido ese día, léase «la cámara de prueba». Detalle al final, en «Aclaración sobre la cámara».

## Estado

| Etapa | Estado |
|---|---|
| 0. Revisión previa | **Hecha** |
| A. Impresora quieta | **en curso**: pasos 1, 2, 3 y 6 hechos; 4 y 5 los hace Samuel; 7 pendiente |
| B. Impresión corta | **hecha, con un punto sin hacer**: faltan los dos cambios de velocidad (la impresión duró 3 min 36 s). Ver el resumen al final |
| C. Pausa y reanudación | pendiente (necesita "autorizo la C") |
| D. Impresora .21 | pendiente (la .21 no respondía en la Etapa 0) |
| E. Datos del modelo | pendiente (faltan `args.yaml`, `results.csv`, `best.pt`) |
| F. Limpiar historial | pendiente (necesita "autorizo la limpieza" y la pregunta sobre la política del curso) |
| G. Cierre | **hecha** (2026-10-09): `RESULTADOS.md`, `KNOWN_LIMITATIONS.md`, `PROGRESO_TELEMETRIA.md` y `HALLAZGOS_PARA_INFORME.md` |

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

## Etapa B: resumen (trabajo 44, 2026-10-08, 19:07:53 a 19:11:29 hora de Colombia)

`Cubo_PETG_2m28s.gcode`, 32 capas de 0,2 mm, un cubo de 6,4 mm en el centro de la cama. Iniciada desde la pantalla de la
.22; la preparación previa (calentar, nivelar) duró ~10 minutos con `print_stats` aún en `standby`. La pausa
automática estuvo en modo `warn` toda la prueba. Nada se envió a ninguna impresora.

**Cierre en la base (solo `SELECT`):** `completed`, inicio 00:07:53 UTC, fin 00:11:29 UTC (3 min 36 s); 206 muestras
(una por segundo, sin huecos de más de 3 s); 32 capas (1 a 32) con 32 fotos y 32 detecciones; 0 alertas. Cadena de
eventos íntegra (75 eventos al cerrar; 82 al generar el reporte, tras unas operaciones con filamento que hizo
Samuel después de imprimir; sigue íntegra). Estado de Klipper al terminar: `complete` y, ~1,5 min después, `standby`.

### Comprobado
- **Fotos por capa:** 32 de 32, 1280×720, ~152 KB cada una. La foto sale 0,29 a 1,77 s (media 0,52) después de que
  PrintWatch detecta el cambio de capa.
- **Latencia de la detección:** del cuadro al resultado, 0,49 a 2,40 s (media 0,87); del cambio de capa al resultado,
  p90 2,5 s y máximo 3,2 s. CPU del worker: pico de ~33 % (un hilo) en cada inferencia, 0 % entre capas; backend
  0,2 a 1,8 %. La carga no estorba a una impresión de 5 s por capa.
- **Mapa de la cama:** la geometría que publica la impresora pone el cubo en (130, 130) mm, con un polígono de
  126,8 a 133,2 mm; durante las capas 3 a 31 el cabezal se movió entre X 127 y 133, Y 127 y 133 mm. Coinciden. La
  malla de ese trabajo es la `default` (10 a 250 mm → cama de 260 × 260 mm).
- **Origen de los eventos del inicio:** `M104 S250`, `M140 S0` y `START_PRINT EXTRUDER_TEMP=250 BED_TEMP=80` →
  `gcode_file`, con la línea del archivo, el desplazamiento y la macro (`via_macro: START_PRINT`). Al final,
  `END_PRINT` → `gcode_file` (`via_macro: END_PRINT`). El paso `standby → printing` → `external` (con
  `job_opened: 44`): PrintWatch no distingue la pantalla de Fluidd. El paso a `complete` → `printer`.
  Los cambios de temperatura de la preparación previa, antes de que hubiera archivo en curso → `external`.
- **Tiempo restante contra el real** (reemplay en segundos): el del laminador (total del nombre del archivo, 148 s,
  menos `print_duration`) dio error medio de 13,5 s (siempre de menos); por capas, 80 s; por avance del archivo,
  265 s (el avance ya marca 7 % al empezar, por el G-code inicial, y por eso sobrestima). Se confirma la elección
  de la Etapa 2: el del laminador. Dos límites: la impresión duró 162,0 s de reloj de la impresora, 14 s (+9,4 %)
  más que los 148 s del nombre, así que en los últimos 14 s marca 0; y los ~52 s de calentamiento de la boquilla
  ocurren con el estado `printing` pero con `print_duration` en 0, así que al principio promete 148 s cuando
  faltan 214 s de reloj de pared. En un trabajo de 6 h no se nota.
- **Filamento:** 94,1 mm → 0,287 g por densidad contra 0,28 g del laminador (+2,5 %, como el +3,1 % del trabajo 43).
- **Lo desplegado hoy funcionó con datos reales:** `print_duration` se guardó en las 206 muestras; el tiempo estimado
  (148 s, origen `filename`) y el peso del laminador (0,28 g) quedaron en la geometría del trabajo; el reporte PDF usa
  el reloj de la impresora (2 min 42 s, +9,4 % sobre el laminador).
- **Reporte PDF:** `docs/laboratorio/reporte_trabajo_44.pdf` (2 páginas).
- **Pausa automática en modo aviso:** 0 eventos `auto_pause.would_pause` (en este trabajo y en total): el modelo no
  marcó ninguna de las 32 capas (0 con defecto, 0 con *spaghetti*). La ruta `warn` solo se probó con la simulada,
  no con datos reales.

### Desmentido o sin poder comprobar
- **El video de la cámara no es de una C922.** Windows ya no tiene conectada la C922 (última llegada: 22-09); la
  cámara en uso es una «USB Camera» genérica (VID 5258, PID 4A55), conectada hoy a las 18:55:39. Antes de eso el
  video salió negro un rato. Encaja con la focal de ~1.500 px (campo de visión de ~52°, no los 78° de la C922): el
  aviso `focal_unusual` era una falsa alarma. La documentación y el nombre «C922 Principal» dicen otra cosa. Falta
  que Samuel confirme qué cámara es físicamente.
- **El modelo no puede ver la pieza con esa cámara en esa posición:** está baja y de frente; se ve la máquina y el
  cabezal, pero no la superficie de la cama con el cubo (6 mm). La detección corrió sobre imágenes sin pieza. Por eso
  «0 defectos» no dice nada sobre la calidad de la pieza. Y la calibración 2 se hizo con otra posición de cámara:
  ya no vale.
- **El mapa de la cama contra un defecto real no se pudo comprobar** (no hubo defectos que ubicar).
- **Latencia pura del modelo (ONNX):** no existe: la detección no guarda el tiempo de inferencia, solo las horas de
  la foto y del resultado. Lo medido es de extremo a extremo.
- **Los dos cambios de velocidad: no se hicieron.** La impresión terminó en 3 min 36 s sin que hubiera tiempo; no hay
  ningún `speed_factor_changed` en la bitácora. Queda pendiente (se puede probar con la impresora en `standby`).
- **El reporte PDF afirma «PrintWatch se unió a esta impresión ya al 7 % (capa 0)»**, y no es cierto: se abrió al
  inicio. La regla (avance de la primera muestra > 2 %) falla en archivos cortos, donde el G-code inicial ya es el 7 %.
  Además el peso sale «0,3 g» (un decimal) cuando el laminador dice 0,28 g.
- **Pre-impresión:** el estado `print_stats` seguía en `standby` ~10 minutos mientras la impresora nivelaba
  (`idle_timeout` en `Printing`, ejes referenciados): PrintWatch abre el trabajo solo cuando Klipper pasa a
  `printing`, así que esa fase no queda en el trabajo (solo en la bitácora, con origen `external`).

### Estado al cerrar (19:15 hora de Colombia)
- Impresora en `standby`, sin archivo, `speed_factor` 100 %, **objetivos de boquilla y cama en 0 (apagados)**. Sigue
  caliente por inercia: boquilla ~177 °C y cama ~67 °C, enfriándose. No se apagó nada desde aquí.
- Después de imprimir, Samuel hizo una operación con filamento (objetivo de boquilla 250 °C de 19:13:27 a 19:14:10;
  sensor de filamento principal `filament_sensor` sin filamento desde 19:14:56): el filamento está descargado.
- Red: SalaSteam_UIS, sin VPN, la .22 responde; la .21 sigue sin responder. Contenedores sanos. Modo de la pausa
  automática: `warn` (volver a `on`: ver la sección «Pausa automática en modo aviso»).

## Pendientes, en orden (versión del 2026-10-08, reemplazada por la última sección de este archivo)

**Con la red del laboratorio (necesitan la impresora o la cámara físicas):**
1. **Confirmar qué cámara es** y dejarla fija. Colocarla de modo que se vea la superficie de la cama y la pieza
   (más alta o más inclinada), y **recalibrarla** desde la web con la impresora quieta (admin). Si no es una C922, la
   focal estimada (~1.500 px) es probablemente la correcta; no fijar 907 px.
2. **Probar los dos cambios de velocidad** (primero desde la pantalla, luego desde Fluidd), con la impresora en
   `standby`, y leer en la bitácora el origen y la hora de cada uno.
3. **Una impresión más larga (unos 10 a 20 min) con una pieza visible** para medir de verdad: fotos con la pieza,
   detecciones, mapa de la cama con defectos, y los cambios de velocidad en vivo.
4. **Etapa C (pausa y reanudación)**: solo con «autorizo la C».
5. **Etapa D (impresora .21)**: cuando se encienda.

**Desde casa, sin la impresora (código, documentación, base local):**
6. **Panel general:** la tarjeta del último trabajo muestra «Capa 0 / 486 · 2 h 45 min» (usa la capa en vivo de la
   impresora quieta y la duración seguida por PrintWatch, no la real) y la miniatura sale negra (reproducir con el
   entorno de demostración). Diagnóstico en la sección «Pendiente para después de la Etapa B». Con pruebas.
7. **Reporte PDF:** quitar el aviso falso de «se unió al 7 %» en archivos cortos (usar la capa de la primera muestra
   o el origen del trabajo, no el avance) y mostrar el peso con más decimales cuando es menor de 1 g.
8. **`capture`:** tratar un cuadro todo negro como «sin señal» y elegir la cámara por nombre o identificador, no por
   índice; corregir en la documentación que la cámara no es la C922 (cuando Samuel lo confirme).
9. **Pausa automática:** decidir si vuelve a `on` o se queda en `warn` hasta tener detecciones reales; cambiar es
   reconstruir solo el backend (funciona sin la impresora; el listener solo no conectará).
10. **Etapa G (cierre):** actualizar `RESULTADOS.md`, `KNOWN_LIMITATIONS.md` y `PROGRESO_TELEMETRIA.md`, y crear
    `docs/laboratorio/HALLAZGOS_PARA_INFORME.md`.
11. **Etapa E (datos del modelo)**, cuando Samuel traiga la carpeta del entrenamiento de Colab o Drive; evaluación con
    pocos hilos y nunca durante una impresión.
12. **Etapa F (limpiar el historial de git)**: solo con «autorizo la limpieza», y antes preguntar si revisó la política
    del curso sobre declarar el uso de herramientas de IA. Sin `git push`.
13. **Precios reales** (filamento por kg y kWh) en «Precios y potencias» desde la web, y revisar las potencias de los
    calentadores (50 W y 300 W siguen sin confirmar).
14. Revisar y, si procede, el SQL opcional del trabajo 34 (`UPDATE print_jobs SET ended_at = (SELECT max(detected_at)
    FROM layers WHERE job_id = 34) WHERE id = 34;`), que solo corrige una duración mal registrada.

## Aclaración sobre la cámara (Samuel, 2026-10-09)

Samuel aclaró que la cámara que se detectó el 2026-10-08 («USB Camera», VID 5258, PID 4A55) era una cámara genérica
que usó mientras tanto, y que la Logitech C922 es la que piensa usar en la implementación final, cuando haga la
detección, por su mejor calidad. Consecuencias:

1. **Las dos calibraciones guardadas (ids 1 y 2) son de la cámara genérica, no de la C922.** Su focal de ~1.500 px
   (campo de visión de ~52° en diagonal) es la de esa cámara. Con la C922 se recalibra; ahí sí se espera cerca de
   907 px a 1280×720 (78° en diagonal) y la opción de fijar la focal y el error por marca sirven para ver cuál
   marca está mal puesta. Las calibraciones viejas quedan como historial: no se borran.
2. **Los 32 cuadros del trabajo 44 y las latencias medidas son de la cámara genérica**, sin la pieza a la vista. Las
   latencias (de la foto al resultado) dependen del modelo y del equipo, no de la cámara; lo que no vale es la
   «detección» como evaluación del modelo: no se ha evaluado con la C922.
3. **El aviso «focal inusual» era una falsa alarma** con esa cámara; ahora es una nota informativa (la focal
   estimada sigue siendo el valor por defecto).
4. **El nombre «C922 Principal» de la cámara 36 no se cambió** en la base ni en la web: es el nombre de la cámara
   final. Su `source_uri` sigue siendo `0` (índice). Para no volver a leer una cámara equivocada cuando se conecte
   la C922, `capture` ya acepta `name:C922`: `UPDATE cameras SET source_uri = 'name:C922' WHERE id = 36;` (cambio
   de configuración que se hace con la C922 conectada, en el laboratorio; no se tocó).
5. **Textos corregidos** donde afirmaban que lo medido era de la C922 (`KNOWN_LIMITATIONS.md`, `PREGUNTAS.md`,
   `MODELO.md`, `RESULTADOS.md`, `PROGRESO_HORA.md`, `PROGRESO_TELEMETRIA.md`). Los comentarios del código que hablan
   de la C922 como referencia (907 px, 78°) siguen: describen la cámara final.
6. **Sin confirmar:** el modelo exacto de la cámara genérica (no cambia nada) y si la C922 sigue funcionando.

## Trabajo desde casa, sin la impresora (2026-10-09)

Sin red de la impresora, sin desplegar ni reconstruir nada, sin `git push`, commits sin coautoría. Un commit por tarea,
todos con pruebas y la web compilando:

| # | Tarea | Commit | Qué quedó |
|---|---|---|---|
| 1 | Panel general, lista de trabajos y «En vivo» | `3333a4b` | La API da `printed_s` (reloj de la impresora, el máximo de `print_duration` por trabajo, una consulta agrupada, sin migración). La tarjeta muestra la capa del propio trabajo (la capa en vivo solo si ese trabajo es el que imprime) y la duración real, con la nota «PrintWatch lo siguió X» cuando se unió tarde; los trabajos viejos muestran solo la duración seguida. Lógica pura en `lib/jobFacts.ts` con 9 pruebas; 1 prueba de API. |
| 2 | Miniatura negra | `3a47c83` | No se pudo reproducir la miniatura negra de Samuel (en la demostración, con navegador, se pintaba bien: 640×480 en una tarjeta de 368×276). Sí se midió que cada video en vivo mantiene una conexión y que a las 6 pestañas con video el navegador deja sin cargar todo lo demás. La miniatura pide ahora una foto cada 2 s (0 flujos, 5 fotos en 7,5 s, medido en la demostración) y el video de «En vivo» se cierra con la pestaña oculta y se reintenta a los 5 s si falla. 3 pruebas (`feedState`). |
| 3 | Reporte PDF | `47e32cd` | El aviso «se unió ya al X %» se decide por la capa de la primera muestra (la 274 del trabajo 43: tardío; la 0 del 44: no); el peso lleva dos decimales bajo 1 g (0,29 g). PDFs 43 y 44 regenerados. 2 pruebas. |
| 4 | `capture` | `2d465ab` | Un cuadro todo negro (media < 2, ningún píxel > 24) cuenta como «sin señal»: no se publica, la capa queda sin foto y el log lo dice una vez. La cámara USB puede elegirse por nombre (`name:C922`, DirectShow con `pygrabber`): si no está conectada, error claro y reintento cada 5 s, nunca otra cámara. 14 pruebas nuevas en `capture/tests` (incluida una del bucle completo con cámara y Redis simulados). **No se reinició `capture`** (ya no estaba corriendo) y no se probó con hardware. |
| 5 | Calibración | `91c26a5` | `focal_unusual` y «con la focal de la C922 una marca no encajaría» pasan de avisos a notas (`notes`); `mark_far_from_corner`, con la focal en uso, sigue siendo aviso. La focal estimada sigue siendo el valor por defecto. |
| 6 | Documentación de la cámara | `2bc14d3` | Textos corregidos donde afirmaban que lo medido era de la C922; «C922 Principal» **no** se cambió en la base ni en la web. Aclaración en este archivo. |
| 7 | Etapa G | (el commit de este resumen) | `RESULTADOS.md` (sección 6 y pendientes), `KNOWN_LIMITATIONS.md` (sección 10), `PROGRESO_TELEMETRIA.md` y `HALLAZGOS_PARA_INFORME.md` (28 puntos). |

**Pruebas al cerrar:** backend 156 pasan (143 al empezar el laboratorio), `capture` 14, web 12 (`vitest`), y la web compila.

**Cambios en este equipo (no están en git):** se reabrió la sesión `wsl -- sleep infinity`; en `frontend/` se instaló
`vitest` (dependencia de desarrollo, sí queda en `package.json`); en `capture\.venv` se instalaron `pygrabber` y `pytest`;
se corrieron la demostración y un segundo servidor de la web para reproducir la miniatura y luego se detuvieron (la base
`printwatch_demo` queda, como siempre). El backend en ejecución en los contenedores sigue siendo el del 8 de octubre con
`AUTO_PAUSE_MODE=warn`: nada de lo de hoy está desplegado.

## Pendientes, en orden

**Necesitan la red del laboratorio, la impresora o la cámara:**
1. **Desplegar lo de hoy:** reconstruir solo el backend (respaldo de la base antes; `docker compose --env-file .env -f
   infra/docker-compose.yml --profile full up -d --build --no-deps backend`) y, si se quiere, volver a `on` la pausa
   automática (borrar `AUTO_PAUSE_MODE=warn` del `.env`; ver «Pausa automática en modo aviso»).
2. **Conectar la C922**, poner su `source_uri` en `name:C922` (`UPDATE cameras SET source_uri = 'name:C922' WHERE id =
   36;`) y reiniciar `capture` (en su entorno ya están `pygrabber` y `pytest`). Comprobar que el cuadro es una imagen
   real y probar tapando el lente que la web pasa a «Sin señal» y que, al destaparlo, vuelve (no se probó con hardware).
3. **Colocar la cámara donde se vea la superficie de la cama y la pieza, y recalibrar con la C922** desde la web con la
   impresora quieta (se espera una focal cerca de 907 px a 1280×720; si no, la tabla de errores dice qué marca falla).
4. **Los dos cambios de factor de velocidad** (primero la pantalla de la impresora, luego Fluidd), con la impresora en
   `standby`, y leer el origen y la hora en la bitácora.
5. **Una impresión más larga (10 a 20 min) con la pieza visible:** fotos con la pieza, detecciones del modelo, mapa de
   defectos, y decidir entonces si la pausa automática vuelve a `on`.
6. **Confirmar con Ctrl+F5** en el navegador real que la miniatura del Panel ya no sale negra.
7. **Etapa C (pausa y reanudación):** solo con «autorizo la C». **Etapa D (impresora .21):** cuando se encienda.

**Se pueden hacer desde casa, sin la impresora:**
8. **Precios reales** (filamento y kWh) en «Precios y potencias» desde la web con la pila local arriba (con
   `wsl -- sleep infinity` abierto); y revisar las potencias de los calentadores (50 W y 300 W siguen sin confirmar).
9. **Etapa E (datos del modelo):** cuando Samuel traiga de Colab o Drive la carpeta del entrenamiento (`args.yaml`,
   `results.csv`, `best.pt`, matriz de confusión); evaluación con pocos hilos de CPU.
10. **Etapa F (limpiar el historial de git):** solo con «autorizo la limpieza», y antes preguntar si revisó la política del
    curso sobre declarar el uso de herramientas de IA. Sin `git push`.
11. **Revisar los commits de hoy** (`git log 1e0211b..HEAD`) y, si procede, el SQL opcional del trabajo 34
    (`UPDATE print_jobs SET ended_at = (SELECT max(detected_at) FROM layers WHERE job_id = 34) WHERE id = 34;`).
12. **Mejoras de código opcionales** (no pedidas): ver el error de reproyección de las marcas antes de guardar la
    calibración (hoy se ve al guardar); guardar el tiempo de inferencia del modelo en cada detección (la latencia pura
    del ONNX no está medida); pruebas automáticas de los componentes de la web.

## Meta final, rama `incidente-web`: Paso 1 (2026-10-09)

**Meta:** que PrintWatch detecte un fallo inminente e intervenga con éxito, mostrando en la web el reporte completo y
los parámetros de la impresora. Reglas: solo lecturas y `SELECT`, sin `git push`, commits sin coautoría.

- **Paso 1 hecho** (solo lectura, **sin cambiar código**): `docs/META_FINAL.md` con (a) la definición de éxito medible,
  (b) la auditoría de brechas leyendo el código real y (c) la propuesta de la regla de «inminente», sin implementarla.
  **Esperando el ok de Samuel** antes del Paso 2 (pantalla de «Incidente»).
- **Lo más importante que salió de la auditoría:**
  - La auto-pausa nunca se ha ejecutado de punta a punta contra la impresora real; la reanudación real ya falló una
    vez (25-09) y su guarda nunca se probó con la Hi; el modelo no se ha evaluado con la cámara final.
  - **Cancelar no existe** (ni endpoint ni guarda ni botón): el Paso 2 lo necesita si el botón «Cancelar» va a estar.
  - **No hay «incidente» como registro:** la cuenta regresiva y el «Abortar» no quedan en la bitácora, y «ejecutada» se
    emite al responder el HTTP, no cuando Klipper queda en `paused`.
  - Solo `spaghetti` puede pausar; la persistencia se cuenta en capas y una capa lenta (24 min medidos) la dispara tarde;
    la cámara no tiene `roi`; el aviso depende de que haya una web abierta.
- **Decisiones que necesita de Samuel** (al final de `META_FINAL.md`): los objetivos de a.2 a a.4, si el Paso 2 incluye
  Cancelar (crear endpoint y guarda), qué abre un incidente, y registrar la cuenta y el aborto en la bitácora y
  confirmar `paused`.

## Meta final, rama `incidente-web`: Paso 2 (2026-10-09, en curso)

Decisiones de Samuel anotadas en `docs/META_FINAL.md`. Reglas: nada se manda a ninguna impresora (todo con la simulada
y la base de pruebas), sin desplegar, sin `git push`, commits sin coautoría. Estado por tarea:

| Tarea | Estado |
|---|---|
| 1. Registro del incidente (backend) | **hecha**: tabla `incidents` (migración `f1a6d3e82b57`, reversible, probada en la base de pruebas: subir, `alembic check`, bajar sin dejar tabla ni índices, subir), servicio `app/services/incidents.py`, eventos `auto_pause.pending/aborted/confirmed/not_confirmed`, confirmación de `paused` con lecturas del estado (20 s), API de incidentes. 168 pruebas del backend pasan (12 nuevas). |
| 2. Cancelar (backend y web) | **hecha**: `POST /printers/{id}/cancel` (solo administrador, con la palabra `CANCELAR` exigida también por el servidor), guarda `cancel_safely` (una orden a la vez compartida con reanudar, enfriamiento de 20 s, solo si la propia impresora dice `printing` o `paused` por una lectura GET), botón con doble confirmación en la web. 179 pruebas del backend y 14 de la web. |
| 3. Pantalla de Incidente (web) | **hecha (falta la revisión en navegador, tarea 4)**: pestaña «Incidentes» por impresora (lista con aciertos / falsos positivos / sin etiquetar), pantalla de detalle (foto con cajas y selector de capa de la racha, clase, confianza, capa y hora, estado completo de la impresora al abrirse y al pausarse, tiempo impreso y restante, línea de tiempo con el estado de la cadena, reporte PDF, Reanudar con la guarda, Cancelar con doble confirmación, Abortar, Ignorar y etiquetar), aviso fijo en todas las pantallas con la marca `(!)` en el título de la pestaña, y los banners de la pausa automática ahora distinguen «enviada», «confirmada» y «NO confirmada». 22 pruebas de la web. |
| 4. Verificación con la demostración | **hecha**: un incidente en modo `warn` y otro en modo `on`, recorridos en el navegador (escritorio y celular), sin errores de consola, capturas y resultados en `docs/laboratorio/incidente/`. Salieron y se corrigieron: el motivo del incidente se juzga por todos sus disparadores (sin eso, en modo `on` faltaba el botón «Abortar»), una galería con las fotos de la racha, textos cortados, y el `favicon.ico` que daba un 404 en consola. |

### Paso 2: resumen y qué hay que hacer al desplegar

**Hecho (cuatro tareas, un commit cada una):** registro de incidentes (tabla, migración reversible, eventos, confirmación
de `paused`, API), cancelar (endpoint, guarda y botón con doble confirmación), pantalla de Incidente (lista, detalle, aviso
fijo, banners) y su verificación con la demostración. Pruebas al cerrar: backend 179 (168 tras la tarea 1, 179 tras la 2), `capture` 14,
web `vitest` 24, `alembic check` sin diferencias en la base de pruebas, y la web compila. Se resolvieron las decisiones de Samuel tal como las dio; las interpretaciones propias
están en `docs/META_FINAL.md` («Cómo se interpretó lo que no estaba definido»). **La regla de la sección c no se
implementó.** Nada de esto está desplegado.

**Contradicciones o dudas con `META_FINAL.md` que quedaron a la vista:** «detección sobre el umbral» (ver arriba: se
limita a `spaghetti` y `layer_shift` con confianza ≥ 0,50, configurable); y que `META_FINAL.md` a.1 no pide un incidente por
cada `stringing` ni `blob`, que con la lectura literal habrían abierto uno.

**Qué hay que hacer al desplegar (en el laboratorio o desde casa, con `wsl -- sleep infinity` abierto), en este orden:**

1. **Respaldo de la base real** (como siempre): `docker exec infra-postgres-1 sh -c 'pg_dump -U "$POSTGRES_USER" -d
   "$POSTGRES_DB"' > storage/respaldo_antes_incidentes_AAAA-MM-DD.sql` (no se versiona).
2. **Migración:** `alembic upgrade head` contra la base real (revisión `f1a6d3e82b57`, solo crea la tabla `incidents`; es
   reversible con `alembic downgrade -1`, que la borra con sus datos). Con el contenedor nuevo se puede hacer así:
   reconstruir el backend (paso 3) y ejecutar dentro `docker exec infra-backend-1 alembic upgrade head`; el backend
   viejo sigue funcionando con la tabla nueva presente. La base de pruebas (`printwatch_test`) **ya está en esa
   revisión**; quien tenga otra base de pruebas debe ejecutar `alembic upgrade head` allí antes de correr las pruebas.
3. **Reconstruir solo el backend:** `docker compose --env-file .env -f infra/docker-compose.yml --profile full up -d
   --build --no-deps backend` (desde la raíz, en WSL). No hace falta tocar `inference-worker`, `capture`, postgres ni redis.
4. **Comprobar:** contenedor `healthy`, `alembic current` = `f1a6d3e82b57 (head)`, `/health` con base y Redis `ok`, y la lista
   `GET /api/v1/incidents` responde (vacía al principio). Con la impresora conectada, el listener debe conectar.
5. **Web:** reiniciar el servidor de la web (`npm run dev` en `frontend/`, o `npm run build` y servir `dist/`) y recargar
   con Ctrl+F5: aparece la pestaña «Incidentes» y el botón «Cancelar impresión».
6. **Variables del `.env` (opcionales):** `AUTO_PAUSE_MODE` sigue en `warn` en el `.env` real hasta que se decida volver a
   `on`; `INCIDENT_CLASSES` e `INCIDENT_MIN_CONFIDENCE` (por defecto `spaghetti,layer_shift` y `0.50`) están documentadas
   en `.env.example`.
7. **Para volver atrás:** `git revert` de los commits de la rama (o volver al commit anterior), reconstruir el backend y,
   si se quiere, `alembic downgrade -1` (borra los incidentes guardados). Dejar la tabla no estorba al backend anterior.

**Lo primero que conviene probar con la impresora real, de menos a más riesgo:** (1) con `AUTO_PAUSE_MODE=warn`, una
impresión normal y ver si aparecen incidentes por una sola foto (y etiquetarlos); (2) la pausa y la reanudación reales
(Etapa C, solo con «autorizo la C»), mirando que el incidente quede `paused` con la confirmación y se cierre como
«Se reanudó»; (3) la cancelación real, solo con una pieza desechable.

## Etapa C (2026-10-09): C0 detenida en el paso 1, sin red del laboratorio

Hora local del equipo: 11:11 a 11:12. Solo lecturas; no se envió nada a ninguna impresora, no se desplegó nada, `AUTO_PAUSE_MODE`
sigue en `warn`.

| Comprobación | Resultado |
|---|---|
| VPN HotspotShield | desconectada (bien) |
| SSID | la primera lectura dijo `SalaSteam_UIS`, pero medio minuto después la interfaz Wi-Fi figura **«desconectado»** (sin SSID) |
| Dirección del equipo | `10.149.43.182` (puerta `10.149.43.17`), no una `192.168.10.x` |
| Ping a 192.168.10.22 y a la puerta del laboratorio 192.168.10.1 | 100 % perdidos |
| `GET http://192.168.10.22:7125/printer/info` | sin respuesta (HTTP 000, 10 s) |
| ARP | sin entrada de la .22 |

El equipo **no está en la red del laboratorio**: no se pudo leer el estado de la impresora (paso 2), así que no se sabe si está en
reposo, y por eso no se desplegó ni se siguió. No se tocaron adaptadores, rutas ni la conexión Wi-Fi.
**Pendiente para reanudar la C0:** que Samuel conecte el equipo a `SalaSteam_UIS` y confirme; se repiten los pasos 1 y 2.

### Etapa C0 repetida (2026-10-09, 11:15 a 11:20 hora local), con el equipo ya en `SalaSteam_UIS`

Solo lecturas hasta el respaldo; la única acción fue reconstruir el backend con la impresora en reposo. Nada se envió a ninguna impresora;
`AUTO_PAUSE_MODE` sigue en `warn`.

| Paso | Resultado |
|---|---|
| 1. Red | SSID `SalaSteam_UIS`, equipo en `192.168.10.102`, VPN desconectada, ping a la .22 con 0 % perdido (3 a 6 ms), `GET /printer/info` 200 (0,05 s). **Estable 60 s**: 7 de 7 lecturas (SSID, ping y GET cada 10 s), 0 fallos |
| 2. Estado real de la .22 | `print_stats.state = standby`, sin archivo, `pause_resume.is_paused = false`, `idle_timeout = Ready`, ejes referenciados (`xyz`), `live_position` X −5,0 / Y 130,0 / Z 10,1; boquilla 33,1 °C y cama 29,0 °C con objetivos en 0; factores 1,0 / 1,0. Cero trabajos `running` en la base |
| 3. Despliegue | Respaldo `storage/respaldo_antes_incidentes_2026-10-09.sql` (8,7 MB, 14 tablas, no se versiona). Reconstruido **solo** `infra-backend-1` (`--no-deps`); postgres, redis y el worker siguen con 5 h de actividad. `alembic upgrade head` dentro del backend nuevo: `e7b3c2a91f04 → f1a6d3e82b57`; `alembic current` = `heads` = `f1a6d3e82b57 (head)`. `/health`: base y Redis `ok`. En el contenedor, `AUTO_PAUSE_MODE = warn`, incidentes `spaghetti,layer_shift` ≥ 0,5; en el `.env`, línea 19 `AUTO_PAUSE_MODE=warn`. Listener conectado a la .22 (`standby`). Rutas nuevas con 401 sin sesión; consulta interna de incidentes: 0 en la base real |
| 4. Cámara | **C922 no conectada** (solo la «USB Camera» genérica, VID 5258). No se cambió `source_uri`. `capture` no está corriendo |

Consecuencia: durante la Etapa C **no habrá fotos ni detecciones** (no hay `capture`); la pausa y la reanudación no las necesitan, pero el incidente
de una pausa real abrirá sin foto asociada.
**Esperando la frase «autorizo la C» escrita por Samuel en este chat** para pasar a la C1.

### Etapa C1 (2026-10-09, 11:40 a 11:47): pieza corta, sin pausa; la prueba real de pausa sigue pendiente

Samuel dio «Autorizo C» y empezó desde la pantalla de la impresora `Cubo_PETG_2m55s.gcode` (35 capas, unos 3 minutos). Era **más corta que los
10 minutos pedidos** y no hubo aviso de «voy por la capa 10 o más», así que **no se hizo C2 ni C3**: no se pausó ni se reanudó nada, y yo no mandé
ninguna orden a la impresora (observación con un `GET` por segundo, guardada en un archivo fuera del repositorio).

Medido (trabajo 45, lecturas de la .22 y base de datos):

| Dato | Valor |
|---|---|
| Inicio de la impresión (`printing`) | 11:40:52 |
| Capa 10 | 11:42:38 (aprox. 6 a 7 s por capa) |
| Fin del trazado / `complete` | 11:44:56 / 11:44:57 |
| Estados vistos | solo `printing` y `complete`; `pause_resume.is_paused` siempre `false`; ningún `error` ni `cancelled` |
| Boquilla durante el trazado (capa ≥ 2) | 248,1 a 252,7 °C (objetivo 250) |
| Cama durante el trazado (capa ≥ 2) | 78,8 a 81,6 °C (objetivo 80) |
| Recorrido de la cabeza (`live_position`, capa ≥ 2) | X −4,4 a 133,3; Y 126,7 a 180,0; Z 0,3 a 57,2 (la Z final es el levantamiento del fin de impresión) |
| Línea base en la capa 10 | pos. (128,9; 128,9; 1,9), boquilla 250,3/250, cama 81,0/80, factor de velocidad 1,0, flujo 1,0, ventilador 0,4, ventilador del hotend 1,0, `print_duration` 53,1 s |
| Después del fin | `complete`, posición (0,0; 260,0; 57,2), `idle_timeout = Ready`, temperaturas bajando (11:47: boquilla 135 °C, cama 75 °C) |
| Registro en PrintWatch | trabajo 45 `completed`, 35 capas, 243 muestras de telemetría, **0 incidentes** (esperable: `AUTO_PAUSE_MODE=warn` y sin `capture`, no hubo detecciones) |

Nota de lo que **no** se midió: segundos hasta `paused`, posición de la cabeza al pausar, temperaturas tras la pausa, y si la reanudación funciona
con esta impresora. Siguen sin datos y no se suponen.

**Para repetir:** Samuel inicia una pieza desechable de 10 minutos o más desde la pantalla de la impresora, se queda junto a ella con la mano cerca
de la parada de emergencia y avisa al pasar de la capa 10. Después, la pausa (C2) la pulsa él en la web y la reanudación (C3) solo si escribe «reanuda».

### Etapa C2 y C3 (2026-10-09, 12:16 a 12:30): pausa real, reanudación real y segunda pausa por filamento atascado

Pieza: `Cubo_PETG_18m27s.gcode` (86 capas), trabajo 46. Samuel la inició en la pantalla de la impresora (12:16:13). Yo no mandé ninguna orden a la
impresora; solo lecturas (`GET` cada segundo, archivo fuera del repositorio) y consultas `SELECT`. `AUTO_PAUSE_MODE=warn` todo el tiempo.

**Medido** (bitácora `printer_events` del trabajo 46 y lecturas de la .22; horas locales):

| Hora | Hecho | Origen en la bitácora |
|---|---|---|
| 12:19:09 | Capa 10; boquilla 248,6/250 °C, cama 80,0/80 °C | lectura |
| 12:19:13,28 | Samuel pulsa «Pausar impresión» en la web (registro del backend «Manual pause requested»); el listener ve `paused` a las 12:19:13,97, **0,7 s después** |
| 12:19:14 | `print_stats.state`: `printing` → `paused` en la capa 10 (cabeza en X 128,0 / Y 122,0 / Z 2,1) | `external` (no hay orden de PrintWatch antes) |
| 12:19:15 a 12:19:22 | La cabeza sube en Z a 49,94; luego va al rincón X 0,0 / Y 260,0 | lectura |
| 12:19:22 | Orden `printer/print/pause` de PrintWatch, pedida por «samuel (web)», `ok: true`, con la impresora ya pausada | `printwatch` |
| 12:19:44 a 12:20:20 | El objetivo de la boquilla baja de 250 a 140 °C (boquilla 228 → 182 °C); cama ~80 °C sin cambio; ventilador de pieza 0,39 igual; ventilador del hotend 1,0 | lectura |
| 12:21:20 | Comprobación previa a reanudar: `paused`, sin `resume_err`, X 0,0 / Y 260,0 dentro de los límites (margen 19 mm en X y 13 mm en Y) | lectura |
| 12:21:26,4 | Samuel pulsa «Reanudar impresión» en la web (registro del backend «Manual resume requested»): a las 12:21:27 el objetivo de la boquilla sube a 250 °C; la boquilla tarda ~45 s en llegar; la cabeza baja a la pieza | lectura |
| 12:21:36 | Orden `printer/print/resume` registrada como `ok: false, error: ReadTimeout`, aunque la reanudación sí ocurrió | `printwatch` |
| 12:22:31 | `paused` → `printing` (64,9 s después del clic); sin error de Klipper; el incidente 1 se cierra como `resumed` por «samuel (web)» | `printwatch` |
| 12:22:39 a 12:23:04 | Capas 11, 12 y 13 (8, 12 y 13 s por capa) | lectura |
| 12:23:05 | `printing` → `paused` en la capa 13 (cabeza en X 131,1 / Y 137,7 / Z 2,5); cabeza al rincón X 0 / Y 260 / Z 49,9; objetivo de boquilla a 140 °C | `external` (sin orden de PrintWatch) |

**Intervención de Samuel:** según él, volvió a pausar porque se atascó filamento y lo está retirando a mano con la impresora pausada. Él no indicó
la hora ni desde dónde pausó (su mensaje llegó con «HH:MM» sin rellenar). La hora que consta es la de la bitácora, 12:23:05. En cuanto al medio:
la bitácora **no** muestra una orden de PrintWatch en ese momento, así que no fue desde la web; entre pantalla de la impresora y aplicación del
fabricante no se puede distinguir con estos registros. La pausa de las 12:19:14 tampoco tiene orden de PrintWatch antes: fue externa; la orden «web»
llegó 8 s después. No se mandó nada desde el equipo durante la intervención.

**Resumen de pausas del trabajo 46:** 2 cambios de estado a `paused` (12:19:14 y 12:23:05), ambos `external`; 1 reanudación, `printwatch`; órdenes de
PrintWatch: pausa (12:19:22, ok) y reanudación (12:21:36, `ReadTimeout`). **Incidentes:** 2, ambos `reason=pause`, modo `warn`, `pause_sent_at`
vacío; el 1 cerrado como `resumed` por «samuel (web)» a las 12:22:31, el 2 en estado `paused` (abierto 12:23:05). Cadena de la bitácora del
printer 35: íntegra (179 eventos revisados, ninguno roto). Sensor de filamento: 0 eventos en el trabajo 46.

**No medido:** los segundos entre el clic en la web y `paused` (la pausa llegó desde fuera de PrintWatch); si el atasco tiene relación con la
pausa o la reanudación previas (no se afirma ninguna causa). **Hallazgo pendiente:** la orden de reanudar tarda más que el tiempo de espera de
PrintWatch (el `ReadTimeout` aparece con la reanudación realizada); la causa en el código no se ha revisado todavía.

**Aclaración de Samuel y lecturas previas a reanudar (12:31, solo lectura).** Samuel cuenta que pulsó Pausar en la web, vio que la cabeza siguió
moviéndose unos segundos y pausó otra vez desde la pantalla de la impresora; después se atascó filamento y lo retira a mano. No dio las horas
(«HH:MM» sin rellenar). Lo que consta: orden web a las 12:19:13,28 (0,7 s hasta `paused`; la orden HTTP no devolvió hasta las 12:19:22,1, mientras la
cabeza subía en Z a 49,94 y se iba al rincón: ese es el movimiento posterior a `paused`). Una segunda pausa pulsada en pantalla entre las 12:19:14
y las 12:19:22 no dejaría rastro (la impresora ya estaba en `paused`); la única pausa externa registrada es la de las 12:23:05, después de la
reanudación. Qué pasó en realidad entre las dos no se puede distinguir con estos registros.

Lecturas a las 12:31: `paused`, `is_paused` true, `resume_err` false, sin mensaje; capa 13/86; `live_position` X 0,0 / Y 260,0 / Z 49,94 (dentro
de los límites; márgenes 19 y 13 mm); boquilla 140,5/140 °C, cama 80,4/80 °C; ventilador de pieza 0,39; sensor de filamento `filament_detected`
true. El estado guardado por Klipper al pausar (`SAVE_GCODE_STATE`) no se puede consultar; `gcode_move` solo da la posición actual. Durante la
reanudación anterior la cabeza pasó por X −18,5 (0,5 mm del límite −19) y por X 279,6 (5,4 mm del límite 285) sin error.
**Riesgo observado en el código y en las lecturas (no probado):** la reanudación tarda ~65 s con el estado aún en `paused`, y la guarda solo
bloquea repeticiones durante 20 s; un segundo clic entre los 20 y los 65 s se enviaría. Mientras tanto la web ya habrá mostrado el `ReadTimeout`
(10,3 s).

**Segundo intento de reanudar (12:37:54), sin orden a la impresora (lecturas de las 12:44).** Samuel pulsó «Reanudar impresión» y la impresora siguió en
pausa. El registro del backend (con hora) muestra `POST /printers/35/resume` → **401 Unauthorized** a las 12:37:54: la sesión de la web había caducado
(el último inicio de sesión fue a las 12:22:02 y el token dura 60 minutos), así que la petición se rechazó antes de llegar a la guarda y no hubo
«Manual resume requested» ni orden a Moonraker. Lo mismo ocurrió con un `POST /pause` a las 12:22:52 (401), 13 s antes de la pausa en pantalla de las
12:23:05: por eso la pausa del atasco acabó pulsándose en la pantalla. Cuánto se ve en la web de ese 401 no se ha revisado.
Además, la propia impresora enfrió la boquilla en pausa: el objetivo pasó de 140 a 0 °C a las 12:38:21, 15 min 16 s después de la pausa de las
12:23:05, y el `gcode_store` de Klipper muestra `COOLING_AFTER_PRINTER_PAUSED: Printer is paused` y `DO_COOLING: Start cooling` justo en ese instante
(el reloj de la impresora va unas 8 h 22 min adelantado; se alinea con las otras marcas). Estado a las 12:44: `paused`, `is_paused` true,
`resume_err` false, `idle_timeout` Ready con `printing_time` 0,0, boquilla 41,5 °C (objetivo 0), cama 79,8 °C (objetivo 80), posición
X 0,0 / Y 260,0 / Z 49,94, capa 13.

### Etapa C (2026-10-09): cierre

La pieza `Cubo_PETG_18m27s.gcode` (trabajo 46, 86 capas) terminó en `complete` a las 13:11:10 después de **dos pausas y dos reanudaciones reales**,
sin ningún error de Klipper ni «Move out of range». Tiempos y valores medidos, lo no medido y los hallazgos por revisar están en
[ETAPA_C.md](ETAPA_C.md). Resumen medido: clic en la web → `paused` en 0,7 s; reanudación en 64,9 s (boquilla desde 140 °C) y en 44,5 s (boquilla ya
caliente); estacionamiento en X 0 / Y 260 / Z 49,94; 2 incidentes, ambos cerrados `resumed` por «samuel (web)»; cadena de la bitácora íntegra (188
eventos). El incidente del 25-09 **no** se repitió en estas dos reanudaciones; no se declara su causa. Pendiente: pausa automática inducida («autorizo la
C»), cancelación real («autorizo cancelar»), decidir `AUTO_PAUSE_MODE`, y los hallazgos de `ReadTimeout` y de la guarda de repeticiones.

### Hallazgos de la Etapa C arreglados en el código (2026-10-09, sin desplegar)

Rama `incidente-web`, un commit por hallazgo (`76e58f2` el 4, `b4e7904` el 1, `3451c3b` el 2, `d425820` el 3) más `bd21511` (la
demostración con la simulada lenta y el recorrido en el navegador). Pruebas: backend 195 pasan contra la base de pruebas, web 44 pasan y
compila. Nada se mandó a ninguna impresora, no se desplegó y no hubo `git push`. Detalle y decisiones en
[ETAPA_C.md](ETAPA_C.md). Lo que ya se comprobó y lo que no: contra la **simulada** (y en un navegador contra la demostración); contra la
Creality Hi real, no.

**Qué hacer al desplegar esto: solo backend y web, sin migración** (no hay cambios de base de datos):
1. Con la impresora **en reposo** (`standby` o `complete`; nunca con una impresión en curso: reconstruir el backend corta el listener).
   Si se quiere, un respaldo de la base como antes, aunque no hay migración.
2. Reconstruir **solo el backend**, con `--no-deps` y `--env-file .env` (igual que `start.ps1`); no tocar Postgres, Redis ni el worker.
   Comprobar `/health` y que `alembic current` siga en `f1a6d3e82b57`. El `.env` puede quedarse como está: la variable nueva
   `JWT_MAX_SESSION_HOURS` es opcional (24 por defecto) y `JWT_EXPIRE_MINUTES` no cambia (60).
3. La web: con el servidor de desarrollo (`npm run dev`) los cambios ya se sirven solos; con una compilación, `npm run build` y
   servir `dist/`. Hay que recargar la pestaña abierta.
4. Compatibilidad entre ambos lados durante el cambio: la web nueva con el backend viejo funciona (la pausa y la reanudación dan 204 y
   la renovación del token da 404 y se ignora); la web vieja con el backend nuevo también (el 202 no la rompe). Mejor backend primero.
5. Con la impresora real, **nada se prueba sin tu autorización**: la pausa y la reanudación reales con estos arreglos (que «Reanudando… N s»
   dure lo que tarda la impresora y que ninguna orden salga como `ReadTimeout`) quedan para otra prueba en una pieza desechable.
6. Las sesiones abiertas antes del cambio siguen valiendo hasta que caduquen y se renuevan sin volver a entrar; como su token no lleva
   `auth_time`, el tope de 24 h les cuenta desde la primera renovación.

### Despliegue de los arreglos de los hallazgos 1 a 4 y fusión en `main` (2026-10-09, 14:07 a 14:20 hora local)

Nada se mandó a la impresora (ni pausa, ni reanudación, ni cancelación); solo `GET` a Moonraker y consultas `SELECT`. Sin `git push`.

| Paso | Resultado |
|---|---|
| Comprobación previa | Equipo en `SalaSteam_UIS` (192.168.10.102), ping a la .22 sin pérdidas (1 a 3 ms). `klippy` ready, `print_stats.state = standby`, sin archivo, `is_paused` falso, `idle_timeout = Ready`, boquilla 33 °C y cama 30 °C con objetivos en 0. Cero trabajos `running` en la base |
| 1. Respaldo | `storage/respaldo_antes_hallazgos_2026-10-09.sql` (11 MB, 15 tablas; `storage/*.sql` está en `.gitignore`) |
| 2. Backend | Reconstruido **solo** `infra-backend-1` (`docker compose --env-file .env … up -d --build --no-deps backend`). Postgres, Redis y el worker conservan su arranque de las 11:30 UTC (8 h de actividad). Sano; `/health`: base y Redis `ok`; `alembic current` = `heads` = `f1a6d3e82b57 (head)` (sin migración); en el contenedor `AUTO_PAUSE_MODE = warn`, `JWT_EXPIRE_MINUTES = 60`, `JWT_MAX_SESSION_HOURS = 24` (por defecto), incidentes `spaghetti,layer_shift` |
| 3. Sesión y listener | Con un token de `samuel` firmado por el propio backend (sin contraseña de por medio; los tokens no se imprimieron ni se guardaron): `POST /auth/refresh` → **200**, mismo `sub` y mismo `auth_time`, 60 min de vida; `GET /auth/me` con el token renovado → 200; un token anterior al cambio (sin `auth_time`) también se renueva y recibe `auth_time`; sin token → 401. El listener se reconectó a la .22 a las 19:09:02 UTC (línea base `standby`, capa 0/0). Cadena de la bitácora de la impresora 35: **íntegra, 190 eventos**, sin ruptura |
| 4. Web | El servidor de desarrollo de la web (`npm run dev`, puertos 5173) ya sirve el código nuevo (Vite lo recarga solo; el log muestra los `page reload`). Para tener lo nuevo en una pestaña abierta: **recargarla con Ctrl+F5** (recarga forzada). Se entra por `http://192.168.10.102:5173`; el `.env` de la web apunta al backend en `192.168.10.102:8000`. Una sesión abierta antes del cambio sigue valiendo y se renueva sola |
| 5. Fusión | `incidente-web` → `main` con merge normal (`--no-ff`, commit `c47f8c1`; `main` no tenía nada propio, 19 commits). Árbol idéntico al de la rama. Sin push |

Pruebas sobre `main`: **web** 44 pasan, tipos, lint y compilación sin errores; **capture** 14 pasan; **backend 194 pasan y 1 falla**:
`tests/test_action_accepted.py::test_an_unreachable_printer_is_a_quick_error_not_a_two_minute_wait`. Esa misma prueba pasó en la rama
(195 de 195) y pasa 3 de 3 veces sola; falló en la corrida de `main`, que coincidió con la compilación de la web. **Causa medida:** en esta
máquina una conexión rechazada (`127.0.0.1:9`) tarda **2,4 s** en fallar y el endpoint espera solo **3 s** por un rechazo rápido
(`ACCEPT_WAIT_SECONDS`); con carga el rechazo llegó más tarde, el endpoint contestó **202** en vez de 502 y la prueba lo detectó.
**Consecuencia real, no solo de la prueba:** pausar con la impresora inalcanzable (red caída, donde conectar tarda hasta 10 s) puede
contestar «aceptada» y la web diría «Pausando…» dos minutos en vez de mostrar el error. Reanudar y cancelar no lo sufren: antes de enviar
leen el estado de la impresora y fallan con 502 (5 s). **Propuesta (sin hacer):** que «aceptada» signifique «la petición ya salió hacia la
impresora» (se puede saber con el seguimiento de httpx) en vez de «pasaron 3 s», con un tope de ~12 s; así un fallo al conectar sigue
llegando como 502 y una pausa que la impresora tarda en responder se acepta al momento. Hay que decidir si se corrige y se vuelve a
reconstruir el backend; lo desplegado hoy tiene la espera de 3 s.

Pendiente: la prueba real de pausa y reanudación con estos arreglos, en una pieza desechable, con autorización aparte.

### Corrección del fallo de la prueba de la impresora inalcanzable y nuevo despliegue del backend (2026-10-09, 14:30 a 14:50 hora local)

Commit `38e12ad` en `main`; sin `git push`. Nada se mandó a ninguna impresora (solo la simulada y la base de pruebas, y `GET` a la .22).

Resuelve el fallo descrito en la sección anterior: se eligió leer el estado antes de pausar en vez de la propuesta de «la petición ya salió» (la lectura previa es la misma que ya usan reanudar y cancelar y no depende de cuánto tarda la máquina).

**Qué cambió.** El endpoint de pausar lee antes de enviar el estado de la impresora (`pause_safely` en `print_guard.py`, el mismo `GET` de 5 s
que usan reanudar y cancelar). Si no responde: 502 al momento, no se envía nada y el fallo queda anotado en la bitácora (orden con
`ok: false`, «no se pudo leer el estado de la impresora, no se envió la orden»). Si responde: sigue igual (202 «aceptada»; la pausa se permite
en cualquier estado, como antes). No se tocó `ACCEPT_WAIT_SECONDS` ni la lógica del 202 de reanudar y cancelar.
**Pruebas:** la de la impresora inalcanzable ya no mide tiempos: pone la espera a cero y comprueba el 502 y la orden anotada como fallida; otra
con la lectura de estado fallando comprueba que nada llega a la impresora simulada (sigue imprimiendo); otra, que una pausa con la simulada
lenta (`--pause-seconds`) contesta 202 sin esperar su respuesta (al contestar, la orden aún no estaba respondida). Sin la lectura previa, las dos
pruebas del 502 fallan (comprobado quitándola).

| Comprobación | Resultado |
|---|---|
| Backend, corrida 1 (sola) | **196 pasan**, 0 fallan (2 min 34 s) |
| Backend, corrida 2 (con la web compilándose tres veces en paralelo) | **196 pasan**, 0 fallan (2 min 47 s) |
| Web | 44 pasan, tipos y lint sin errores, 3 compilaciones sin errores |
| Antes de reconstruir | Red `SalaSteam_UIS`; `klippy` ready, `print_stats.state = standby`, sin archivo, `is_paused` falso, `idle_timeout = Ready`; 0 trabajos `running` |
| Respaldo | `storage/respaldo_antes_pausa_estado_2026-10-09.sql` (11 MB, 15 tablas; `.gitignore`) |
| Reconstrucción | Solo `infra-backend-1` (`--no-deps`, `--env-file .env`); Postgres, Redis y el worker con su arranque original (11:30 UTC) |
| `/health` | base y Redis `ok` |
| `alembic current` | `f1a6d3e82b57 (head)` = `heads` (sin migración) |
| `AUTO_PAUSE_MODE` | `warn` en el contenedor y en `.env` (línea 19) |
| Código nuevo en el contenedor | `pause_safely` presente |
| Sesión | `POST /auth/refresh` → 200 con un token de `samuel` (mismo `sub` y `auth_time`, 60 min); `/auth/me` 200; token anterior al cambio 200; sin token 401 |
| Listener | Reconectado a la .22 a las 19:44:28 UTC, línea base `standby`, capa 0/0 |
| Cadena de la bitácora | **íntegra, 191 eventos** |

**No comprobado en el despliegue:** una pausa real (no se manda nada a la .22). El comportamiento nuevo de pausar con la impresora inalcanzable
queda cubierto por las pruebas con la simulada; con la impresora real se verá en la prueba de pausa y reanudación con autorización aparte.

### Etapa C2, C0 (2026-10-09, 17:20 a 17:50): red, entorno y la pieza de 45 min que PrintWatch no registró

Solo lecturas hacia la impresora (`GET`, pruebas TCP y ping); nada se mandó a la .22 (ni pausa, ni reanudación, ni cancelación). Sin `git push`.

**Configuración de red (correcta, no se cambia).** Cable a `SalaSteam_UIS` para la impresora y Wi-Fi a `ComunidadUIS` para internet. La métrica del
cable la puso Samuel en 100 (a mano, `AutomaticMetric` desactivada); la VPN (`HotspotShield`) está desconectada.

| | Cable (`Ethernet 4`, Realtek USB GbE, 100 Mbps) | Wi-Fi (`ComunidadUIS`, Intel AC 9560) |
|---|---|---|
| IP | 192.168.10.105/24 | 10.13.182.119/22 |
| Puerta de enlace | 192.168.10.1 | 10.13.180.1 |
| Métrica de interfaz / ruta predeterminada total | **100** / 100 | 35 / 35 |
| DNS (en el orden en que Windows los consulta) | 192.168.10.1 (segundo) | **10.0.48.18 (`DC1.uis.local`), 10.0.48.19, 8.8.8.8 (primero)** |
| Sale por aquí | la .22 (origen 192.168.10.105) | internet (origen 10.13.182.119) |

Con las métricas en 35 y 35 (antes del cambio) las dos rutas predeterminadas empataban y aparecieron fallos intermitentes: `www.google.com` y
`www.wikipedia.org` fallaron una vez cada uno; se midió que el DNS del cable (192.168.10.1) **no resolvió** `www.google.com` (7,4 s hasta el
tiempo de espera) mientras 10.0.48.18 y 8.8.8.8 sí (51 y 14 ms). Con la métrica del cable en 100: `google.com` 5 de 5 bien y `wikipedia.org` 5 de 5
bien (0 fallos de 10). No se demostró que el DNS fuera la causa de los fallos anteriores; solo se midió lo anterior.

**`frontend/.env`:** ahora `VITE_API_BASE_URL=http://localhost:8000` (antes `http://192.168.10.102:8000`, una IP del Wi-Fi anterior que ya no existe).
Ese archivo **no va en git** (`frontend/.gitignore`). Se reinició el servidor de desarrollo de la web. El backend admite cualquier origen
(`CORS_ALLOW_ORIGINS=*`), así que no falta ninguno. Comprobado en Edge contra el backend real desde `http://localhost:5173`: el formulario con una clave
incorrecta hace `POST http://localhost:8000/api/v1/auth/login` y recibe 401 con la cabecera CORS `*` (el formulario dice «Usuario o contraseña
incorrectos.», sin error de red ni de CORS); una sesión con un token de `samuel` firmado por el backend (sin usar su contraseña) carga el panel, la vista
en vivo, los incidentes y la bitácora con 65 llamadas a la API, todas 2xx, el WebSocket abierto en `ws://localhost:8000` y sin errores de consola ni
peticiones fallidas. **No** se probó el inicio de sesión con la contraseña real.

**Muestreo de 10 minutos (17:36:59 a 17:46:44, una muestra cada 15 s, solo lecturas):** 40 muestras; **0 fallos TCP** a la .22:7125; **0 lentas** (más
de 200 ms); tiempo de conexión mínimo 0 ms, mediana 1 ms, máximo 48 ms; origen siempre 192.168.10.105. **Listener:** 0 reconexiones en la ventana (el último
`monitor_connected` es de las 17:24:44; la única línea del listener en el log es el cambio de estado de la impresora `complete → standby` a las 17:44:17,
que no es una caída). Al cierre: `GET` a la .22 → `standby`, sin archivo, sin pausa; `/health` ok; `alembic` en `f1a6d3e82b57`; cadena de la bitácora
**íntegra, 266 eventos**. Entre las 17:28 y las 17:46 la bitácora recogió 16 cambios de objetivos de temperatura, 30 cambios del sensor de filamento y el
`complete → standby`, todos de origen `external` y **sin ninguna orden de PrintWatch** (coherente con manejo en la propia impresora; no confirmado).
Antes del muestreo, del reanudarse el equipo (17:11:47) a las 17:24:44, el listener se cayó y reconectó 14 veces y hubo pings y conexiones TCP fallidos a la .22;
la causa no está demostrada (coincide con la reconfiguración de la red tras reanudar el equipo).

**Hallazgo: la pieza de 45 min que PrintWatch no registró (entre las 14:44 y las 17:12).**
- Historial de Moonraker: `obj_1_highblending-A1-mini.stl_PETG_45m8s.gcode`, `completed`, 45,4 min de impresión.
- En PrintWatch no hay ningún trabajo después del 46, ni ningún cambio de estado, entre `monitor_connected` a las 14:44:28 (`standby`) y el siguiente a las
  17:12:14 (ya `complete`). El log del backend no tiene ninguna línea del listener entre `connected` (14:44:28) y un `ConnectionClosedError` a las 17:12:03.
- **Demostrado con el registro de Windows:** el equipo estuvo **suspendido de las 14:50:54 a las 17:11:47** (Kernel-Power id 42 a las 14:51:03, motivo «Button or
  Lid»; Power-Troubleshooter: suspensión 19:50:54 UTC, reactivación 22:11:47 UTC, origen «botón de inicio/apagado»; el reloj del sistema saltó de 19:51:04 UTC a
  22:11:45 UTC; red desconectada a las 14:50:29 y reconectada a las 17:11:46). Con el equipo suspendido el backend, el listener y WSL no se ejecutaban, así que
  PrintWatch no pudo ver nada de lo que ocurrió en la impresora en ese lapso. El plan de energía activo («Máximo rendimiento») tiene la suspensión por inactividad en
  0 (nunca) en corriente alterna y continua: la suspensión no fue por inactividad.
- **Qué se deduce y qué no:** PrintWatch estuvo despierto solo de las 14:44:28 a las 14:50:54 sin ver ningún cambio de estado, y el estado era `standby` a las
  14:44; una pieza de 45 min no cabe ahí, así que se imprimió mientras el equipo estaba suspendido o antes de las 17:12. **No se sabe a qué hora exacta**: el reloj
  de la impresora no es fiable; aplicando el desfase medido a las 12:16 (+8 h 22 min 41 s) saldría de las 16:08 a las 17:04, **solo una estimación sin verificar**.
  Tampoco se sabe qué provocó la suspensión (tapa o botón de encendido; el registro no lo distingue).
- Consecuencia: esa pieza no tiene trabajo, capas ni telemetría en PrintWatch. Para la C2: que el equipo no se suspenda durante la prueba (no cerrar la tapa ni pulsar
  el botón de encendido).

### Diagnóstico de la cámara: no se veía en la web (2026-10-09, 18:00 a 18:30)

Solo lecturas hasta arrancar `capture`; nada se mandó a la impresora; no se tocó el backend, la base ni el código de la web (no se reconstruyó nada).

**Causa demostrada: `capture` no estaba corriendo.** `start.ps1` no lo arranca a propósito (avisa de que es un paso manual: `capture\.venv\Scripts\python.exe -m capture.main`,
sin argumentos; la cámara sale de la base). No había ningún proceso `python`. La última vez que corrió fue el 2026-10-08 (Windows registra el uso de la cámara desde las
18:55; el último fotograma es de las 19:18:04). Redis conserva ese fotograma sin caducidad (`latest_frame:36` y `latest_frame_at:36`, TTL −1), con **22,9 h** de antigüedad.

| Eslabón | Evidencia |
|---|---|
| Vista en vivo, antes | `/stream` 200 (`multipart/x-mixed-replace`) pero con la imagen de reemplazo de 640×480 que dibuja el backend cuando el fotograma tiene más de 15 s («Sin senal: el servicio de captura no esta enviando video», letra pequeña): la imagen no falla, así que el `VideoFeed` no pinta su propio «Sin señal» (solo lo hace si la imagen da error) |
| Miniatura del panel, antes | `/snapshot` 200 (141 886 bytes, `X-Frame-Age-Seconds: 82330`): la web lo da por viejo (más de 15 s, `feedState.ts`) y pinta «Sin señal» |
| Cámara | Abre con el mismo código de `capture`: por **índice 0** (backend por defecto, MSMF) abre en 4,4 s la primera vez (0,59 s después), primer fotograma en 62 a 79 ms, 1280×720, ~30 fps, brillo normal, no vacío ni negro. Por **nombre** (`name:USB Camera`, DirectShow) abre pero entrega **0×0** y no lee. El índice 1 no existe. Ningún otro proceso la tenía (Windows conserva un «en uso» antiguo de `python.exe` desde el 8 de octubre: es un resto del registro tras terminar el proceso de golpe) |
| Con `capture` corriendo (18:11 a 18:28) | Redis: fotograma nuevo cada ~0,17 s, edad de 0,35 a 0,69 s; `/snapshot` 200 con edad 0,2 a 0,4 s; el primer fotograma de `/stream` es real (1280×720); la web pinta el video en vivo y la miniatura, sin «Sin señal» ni errores de consola |
| Después | `capture` se detuvo a las 18:28 (Samuel lo arrancará en su terminal para la C2); la cámara quedó libre (abre en 0,59 s y se cierra) |

**Observaciones.** Lo que muestra la cámara **no es la cama**: se ve la base de la impresora y su pantalla (en otra captura, una mano), así que la calibración de cámara y cama no
vale con esta cámara y esta posición. La fila de la cámara en la base se llama **«C922 Principal»** (`usb`, `source_uri = 0`) aunque la conectada es la genérica «USB Camera»
(VID 5258, PID 4A55); el modo por nombre (`name:C922`) está sin probar con la C922 real. Una advertencia de consola de la web imprimió un token de `samuel` firmado por el backend
(la web pone el token en la URL del WebSocket); caduca a la hora.

**Pendientes:**
1. Un aviso claro en la web de «captura detenida» en lugar del texto diminuto de la imagen de reemplazo (hoy el backend manda una imagen con 200 y la web no distingue el caso).
2. Un script que arranque `capture` comprobando antes que la cámara abre (y avise si no).
3. Reposicionar la cámara y recalibrar con la C922 (probar antes `name:C922`).

**Para la C2 (con `capture` corriendo).** Se mide además, con solo lecturas, qué capas se capturaron (por capa y hora), si hubo huecos en la pausa y la reanudación, y cuál fue la primera
captura tras reanudar y cuánto tardó: consultas en [c2_capturas.sql](c2_capturas.sql) (probadas contra los trabajos 44 y 46). En modo `warn` nada actúa. Las capturas se disparan por capa
(`layer_ready`), así que durante la pausa no se espera ninguna; el video en vivo de Redis sí debería seguir renovándose (edad menor de 2 s).
