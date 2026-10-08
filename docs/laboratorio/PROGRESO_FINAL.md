# Progreso final (prompt maestro, etapas 0 a G)

Reglas: solo lectura sobre las impresoras (GET, WebSocket de lectura, SELECT, lectura de logs); sin `git push`;
commits sin línea de coautoría; las etapas avanzan solo con la confirmación escrita de Samuel; la C y la F
solo con la frase exacta ("autorizo la C", "autorizo la limpieza").

## Estado

| Etapa | Estado |
|---|---|
| 0. Revisión previa | **Hecha** |
| A. Impresora quieta | **en curso**: pasos 1, 2, 3 y 6 hechos; 4 y 5 los hace Samuel; 7 pendiente |
| B. Impresión corta | pendiente |
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
