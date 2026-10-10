# Etapa C: pausa y reanudación reales de la impresora (2026-10-09)

Impresora 35 «Creality Hi-3422» (192.168.10.22), Klipper/Moonraker. Rama `incidente-web`, backend desplegado con la migración
`f1a6d3e82b57`, `AUTO_PAUSE_MODE=warn` todo el tiempo. **PrintWatch no inició, canceló ni movió ninguna impresión**: la pieza la inició Samuel
desde la pantalla de la impresora; las pausas y reanudaciones desde la web las pulsó Samuel; el resto fueron acciones suyas en la pantalla.
La observación fue solo de lectura (un `GET` por segundo a Moonraker y consultas `SELECT`). Horas locales (Colombia).

Pieza: `Cubo_PETG_18m27s.gcode`, 86 capas, trabajo 46 (12:16:13 a 13:11:10, `completed`, 86 capas y 3 289 muestras de telemetría en la base).
Antes hubo una prueba corta, `Cubo_PETG_2m55s.gcode` (trabajo 45, 11:40 a 11:44), sin pausa.

## Cronología medida

| Hora | Hecho | Fuente |
|---|---|---|
| 12:16:13 | `standby` → `printing` (inicio desde la pantalla) | bitácora |
| 12:19:09 | Capa 10; boquilla 248,6/250 °C, cama 80,0/80 °C | lecturas |
| 12:19:13,28 | Clic en «Pausar impresión» (web) | registro del backend |
| 12:19:13,97 | `printing` → `paused` visto por el listener (**0,7 s** después del clic) | registro del backend |
| 12:19:14 a 12:19:22 | La cabeza sigue moviéndose: Z 2,1 → 49,94 y luego al rincón X 0,0 / Y 260,0. La orden HTTP no devuelve hasta las 12:19:22,1 | lecturas, bitácora |
| 12:19:27 | Objetivo de la boquilla 250 → 140 °C (lo hace la impresora) | bitácora |
| 12:21:26,4 | Clic en «Reanudar impresión» (web); a las 12:21:27 el objetivo de la boquilla pasa de 140 a 250 °C | registro del backend, bitácora |
| 12:21:36,7 | La orden se registra con `ReadTimeout` (502) a los 10,3 s, aunque la reanudación sigue en marcha | registro del backend |
| 12:22:31 | `paused` → `printing` (**64,9 s** después del clic); incidente 1 cerrado `resumed` por «samuel (web)» | bitácora |
| 12:22:52 | `POST /pause` desde la web rechazado con 401 (sesión caducada) | registro del backend |
| 12:23:05 | `printing` → `paused` en la capa 13, origen `external` (pantalla o app, por el atasco de filamento); se abre el incidente 2 | bitácora |
| 12:37:54 | «Reanudar» desde la web rechazado con 401 (sesión caducada); no se envió nada a la impresora | registro del backend |
| 12:38:21 | La impresora baja el objetivo de la boquilla de 140 a 0 °C (15 min 16 s después de la pausa; `COOLING_AFTER_PRINTER_PAUSED`) | bitácora, `gcode_store` |
| 12:51:57 a 12:54:25 | Acciones de Samuel en la pantalla: boquilla a 250 °C, cabeza por X −18,5 / Y 130, objetivo a 140 y luego a 250 | lecturas (no hay órdenes de PrintWatch) |
| 12:54:26,8 | Clic en «Reanudar impresión» (web) con sesión nueva | registro del backend |
| 12:54:37,1 | `ReadTimeout` (502) a los 10,3 s | registro del backend |
| 12:55:11 | `paused` → `printing` (**44,5 s** después del clic); incidente 2 cerrado `resumed` por «samuel (web)» | bitácora |
| 13:11:10 | `printing` → `complete` | bitácora |

## Valores medidos

| Magnitud | Valor |
|---|---|
| Clic en la web → `paused` | 0,7 s |
| Duración del movimiento posterior a la pausa (hasta que la orden HTTP vuelve) | ~9 s |
| Posición de la cabeza al pausar (1.ª pausa, capa 10) | X 128,0 / Y 122,0 / Z 2,1 |
| Posición de estacionamiento | X 0,0 / Y 260,0 / Z 49,94 (márgenes a los límites: 19 mm en X, 13 mm en Y) |
| Posición de la cabeza al pausar (2.ª pausa, capa 13) | X 131,1 / Y 137,7 / Z 2,5 |
| Temperatura de la boquilla | 252 °C al pausar; 189 °C a los 60 s en pausa (objetivo 140); 41,5 °C a los 21 min (objetivo 0) |
| Temperatura de la cama durante las pausas | 79,4 a 81,0 °C (objetivo 80 sin cambio) |
| Ventilador de pieza | 0,39 antes y después de la pausa (sin cambio) |
| Reanudación 1 (desde 140 °C) | 64,9 s; boquilla 140 → 250 °C en ~45 s; sin error de Klipper |
| Reanudación 2 (boquilla ya a 250 °C por la pantalla) | 44,5 s; sin error de Klipper |
| Recorrido de la cabeza al reanudar | pasa por X −18,5 (0,5 mm del límite −19) y X 279,6 (5,4 mm del 285), con Y 130 y Z ~5 |
| Capas tras la reanudación 1 | 10 → 13 a ~8 a 13 s por capa |
| Capas tras la reanudación 2 | 13 → 86 a ~12 a 13 s por capa; boquilla 248,2 a 252,4 °C, cama 77,9 a 80,6 °C |
| Mensajes de error de Klipper, `resume_err` y «Move out of range» | **ninguno** en todo el trabajo |
| Incidentes | 2 (`reason=pause`, modo `warn`, sin orden de pausa de PrintWatch), ambos cerrados `resumed` por «samuel (web)» |
| Cadena de la bitácora | íntegra: 188 eventos revisados, ninguno roto |

## Lo que no se midió o no se probó

- **Segundos del clic en pantalla a `paused`**: la pausa de las 12:23:05 fue externa y no hay hora del toque.
- **Qué provocó el atasco de filamento**: no se afirma ninguna causa, ni relación con las pausas o reanudaciones previas.
- **Fotos y detecciones**: `capture` no estaba corriendo (C922 no conectada), así que no se comprobó que lleguen capas con foto tras la reanudación ni que un incidente tenga foto asociada.
- **Posición guardada por Klipper al pausar**: no se puede consultar; solo se vio por dónde se movió la cabeza al volver.
- **Pausa automática por detección** (`AUTO_PAUSE_MODE=on`) y **cancelación real**: no se probaron.
- **Duración del enfriamiento por pausa prolongada**: se midió una vez (15 min 16 s); no se sabe si es un temporizador fijo.

## Hallazgos: resueltos en el código (rama `incidente-web`, 2026-10-09)

Los cuatro quedaron arreglados con pruebas contra la impresora **simulada** y la base de pruebas, un commit por
hallazgo; no se mandó nada a ninguna impresora real, no se desplegó y no hubo `git push`. **Falta comprobarlos con la
Creality Hi real** (solo se simuló su tardanza); hasta entonces es lo supuesto a partir de lo medido el 2026-10-09.

| # | Hallazgo | Estado | Commit | Qué se hizo |
|---|---|---|---|---|
| 1 | `ReadTimeout` al reanudar: la web veía 502 y la bitácora `ok: false` aunque la impresora obedecía | Resuelto | `b4e7904` y `38e12ad` | La orden va en segundo plano con 120 s para la respuesta (10 s para conectar). Pausar, reanudar y cancelar esperan 3 s por si hay un rechazo rápido (sigue llegando como 502) y responden **202 «aceptada»**. La bitácora anota la orden como enviada (`ok` vacío) y, si falla después, añade una segunda entrada. La web (controles, pantalla de incidente y aviso de pausa automática) muestra «Reanudando… N s» hasta que el estado de la impresora cambia o pasan 2 minutos, y entonces dice que la orden se envió pero el estado no cambió, sin llamarlo error. **Corrección posterior (`38e12ad`):** la espera de 3 s para «aceptada» no distingue una impresora que no responde de una que tarda (con carga, o con la red caída, un fallo de conexión llegaba tarde y salía 202). Ahora pausar lee antes el estado de la impresora (`GET`, 5 s como mucho, el mismo mecanismo que reanudar y cancelar): sin respuesta devuelve 502 al momento, no envía nada y anota el fallo en la bitácora; con respuesta sigue igual (202). `ACCEPT_WAIT_SECONDS` y el 202 de reanudar y cancelar no cambian |
| 2 | La guarda solo bloqueaba 20 s; un segundo clic entre los 20 y los 65 s se enviaba | Resuelto | `3451c3b` | Una orden de reanudar o cancelar que la impresora aún no ha respondido cuenta como «en curso» (tope de 90 s) y otra del mismo tipo se rechaza con 409. Una orden ya respondida o fallida no bloquea: se puede reanudar una pausa nueva (como la del atasco, 34 s después). La simulada acepta `--pause-seconds` y `--resume-seconds`; con la regla anulada, la prueba deja pasar el segundo clic |
| 3 | Sesión web caducada a mitad de la impresión: 401 sin explicación | Resuelto | `d425820` | El token se queda en 60 min y se **renueva** (`POST /auth/refresh`) cuando quedan menos de 30 min, cada 5 min y al volver a la pestaña; la sesión termina 24 h después del login que la inició (`JWT_MAX_SESSION_HOURS`, por defecto 24). Un 401 en una petición con token cierra la sesión y el login dice «Tu sesión caducó. Inicia sesión de nuevo.»; usuario o clave mal puestos siguen diciendo lo suyo |
| 4 | La pausa pedida desde la web quedaba como `external` en la bitácora | Resuelto | `76e58f2` | La orden se anota **antes** de enviarla, así aparece antes del cambio de estado y este queda atribuido a `printwatch`; la ventana de atribución pasa de 60 a 120 s. La cadena de hashes sigue íntegra (la bitácora es solo de añadir) |

Decisión del hallazgo 3 (por qué renovar y no alargar el token): alargarlo deja un token robado vivo más tiempo;
renovarlo mantiene la hora de vida y deja una sesión activa viva solo mientras la web esté abierta, con un tope total
de 24 h para que un token robado no se pueda renovar para siempre. Efecto lateral cuidado: el token que ve cada
pantalla no cambia al renovarse (el renovado va al cliente de la API y al almacenamiento), así que ninguna página se
recarga y el WebSocket no se reconecta. Un token anterior al cambio no tiene `auth_time`: su sesión cuenta desde la
primera renovación.

Comprobado además en el navegador (Edge) contra la demostración: `docs/laboratorio/hallazgos_etapa_c/`.

Sin cubrir: `fetchSnapshot` (la miniatura de cámara) llama a `fetch` directamente y no pasa por el aviso de sesión
caducada; la pausa desde la web sigue sin guarda contra repeticiones (no se pidió).

## ¿Se repitió el incidente del 25-09?

No: en las dos reanudaciones reales no apareció «Move out of range» ni ningún error de Klipper, la cabeza volvió a la pieza y las capas siguieron.
No se declara causa del incidente del 25-09.

## Qué sigue

1. **Pausa automática inducida** con «autorizo la C» otra vez (modo `on`, en una pieza desechable).
2. **Cancelación real** probada por separado, solo si Samuel escribe «autorizo cancelar».
3. **Decidir `AUTO_PAUSE_MODE`** (por ahora `warn`).
4. Desplegar los arreglos de los hallazgos 1 a 4 (solo backend y web, sin migración; ver `PROGRESO_FINAL.md`) y probarlos con la
   impresora real, con tu autorización.
