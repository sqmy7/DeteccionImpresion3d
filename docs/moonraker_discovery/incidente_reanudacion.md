# Incidente de reanudación del 25-09-2026 (Creality Hi-3422, job 35)

**Estado:** análisis parcial con la evidencia disponible sin acceso a la impresora. Faltan los logs de
la impresora y la configuración de sus macros (ver "Qué falta y cómo obtenerlo").

## Resumen

La impresión `BOX FINAL lista pa imprimir_PETG_2h5m.gcode` se pausó a mano desde la API de Moonraker
cuando ya estaba en su **última capa (125 de 125)**. Al reanudarla, la impresora imprimió unos 7,5
segundos y Klipper detuvo el trabajo con:

```
Move out of range: 292.424 249.610 28.401 [18941.126]
```

Es decir, un movimiento hacia X = 292,4 mm, fuera de la cama de 260 × 260 mm. La causa no está
determinada.

## Fuentes de evidencia usadas

1. **Base de datos de PrintWatch** (tablas `print_jobs` y `layers`): el listener de Moonraker registró
   cada cambio de capa y el momento en que Klipper pasó a `error`.
2. **Tres consultas a `GET /printer/objects/query?print_stats`** hechas durante el incidente (respuestas
   textuales abajo). `eventtime` es el reloj monotónico de Klipper, en segundos.
3. **El backend de PrintWatch**: un intento de reanudación por `POST /api/v1/printers/35/resume`
   devolvió HTTP 502 con el detalle de error vacío.

### Respuestas de Moonraker registradas

| # | Momento | `eventtime` | `state` | `print_duration` | `total_duration` | `filament_used` | `z_pos` |
|---|---|---|---|---|---|---|---|
| 1 | Tras la pausa | 12494,434 | `paused` | 7448,437 | 7520,635 | 18494,370 | 49,929 |
| 2 | Tras el intento fallido del backend | 12593,514 | `paused` | 7448,437 | 7619,714 | 18494,370 | 49,929 |
| 3 | Tras la reanudación directa | 12648,693 | `error` | 7455,977 | 7659,916 | 18494,264 | 28,431 |

Mensaje de la consulta 3: `{"code":"key243","msg":"Move out of range: 292.424 249.610 28.401 [18941.126]", "values":[292.424, 249.610, 28.401, 18941.126]}`
(el formato `code`/`key243` no es de Klipper estándar; parece propio de Creality).

### Datos de la base de datos

| Dato | Valor (UTC) |
|---|---|
| Inicio del job 35 (`started_at`) | 2026-09-25 22:12:27,40 |
| Capa 125, la última (`layers.detected_at`) | 2026-09-26 00:16:21,74 |
| Ritmo de las últimas capas | una cada ~17 s (capas 114-125) |
| Fin del job, estado `failed` (`ended_at`) | 2026-09-26 00:20:07,09 |

## Lo que la evidencia demuestra

- **Los relojes coinciden.** Entre `started_at` y `ended_at` pasaron 7659,69 s; Moonraker reportó
  `total_duration` = 7659,92 s al terminar. La diferencia (0,2 s) permite convertir `eventtime` a hora
  real: `UTC(e) = 00:20:07,09 − (12633,72 − e)` segundos.
- **Línea de tiempo** (UTC; en Colombia restar 5 horas, o sea la tarde del 25-09):

  | Hora UTC | `eventtime` | Hecho | Cómo se obtuvo |
  |---|---|---|---|
  | 00:16:21,7 | — | Empieza la capa 125 de 125 | `layers.detected_at` |
  | 00:16:35,6 | 12422,2 | Empieza la pausa | consulta 1: `eventtime − (total − print)` |
  | entre 00:17:47 y 00:19:27 | entre 12494 y 12594 | Intento de reanudar vía backend (502) | orden de las consultas |
  | 00:19:26,9 | 12593,5 | La impresora **sigue pausada** | consulta 2 |
  | 00:19:59,5 | 12626,2 | La impresión se reanuda | consulta 3: `print_duration` avanzó 7,54 s |
  | 00:20:07,1 | 12633,7 | Error y fin del trabajo | `ended_at` y `total_duration` de la consulta 3 |

- **La pausa ocurrió en la última capa**, ~14 s después de que empezara. Con capas de ~17 s, quedaban
  unos 3 s de capa y después el código de fin del archivo (*end G-code*).
- **Tras reanudar hubo 7,5 s de impresión** antes del error.
- **El filamento no avanzó: retrocedió 0,106 mm** (18494,370 → 18494,264). En esos 7,5 s hubo una
  retracción neta y no extrusión, típico de movimientos de fin de impresión o de una macro, no de
  imprimir una capa.
- **El intento de reanudar por el backend no reanudó la impresión**: después de ese intento la
  impresora siguió en `paused` (consulta 2). La única reanudación con efecto observado es la
  posterior, hecha directamente contra Moonraker.

## Interpretación (no demostrada)

Ordenadas de más a menos probable con lo que se sabe hoy:

1. **El código de fin del archivo (o una macro que llama) contiene un movimiento a X ≈ 292 mm.** Encaja
   con: la pausa fue en la última capa, después de reanudar solo hubo 7,5 s de actividad, el filamento
   se retrajo y la Z del movimiento (28,4) está un poco por encima de la última capa (25,0), como el
   "levantar Z y estacionar" típico del final. Si es así, el error no lo causó la reanudación: habría
   pasado igual al terminar. Se comprueba leyendo el final del G-code y el historial de otras
   impresiones con el mismo perfil.
2. **Las macros de pausa/reanudación dejaron un estado de coordenadas inconsistente** (por ejemplo,
   modo relativo/absoluto o una posición guardada restaurada con desfase), y el siguiente movimiento
   del archivo se interpretó mal. Se comprueba leyendo las macros `PAUSE` y `RESUME` del `printer.cfg`.
3. **Dos reanudaciones seguidas** (la del backend y la directa). Es la hipótesis que se planteó en el
   momento, pero **la evidencia va en contra**: después del intento del backend la impresora seguía
   pausada. Solo `moonraker.log` puede confirmar si esa petición llegó a la impresora.

El valor `z_pos` de la tabla (49,9 durante la pausa) no se usa como evidencia: ya se comprobó que en
este firmware ese campo se queda desfasado (ver `docs/KNOWN_LIMITATIONS.md`, punto 1). Si fuera
correcto, indicaría que la macro de pausa levanta el cabezal unos 25 mm.

## Qué falta y cómo obtenerlo

Todo se obtiene **solo leyendo** (peticiones GET); el script `backend/scripts/moonraker_discovery.py`
lo guarda en esta carpeta en una sola corrida:

| Evidencia | Fuente en Moonraker | Riesgo de pérdida |
|---|---|---|
| Peticiones HTTP recibidas entre las 00:16 y las 00:21 UTC (¿llegó el `resume` del backend?, ¿desde qué cliente?) | `moonraker.log` | Alto: rota periódicamente |
| Comandos y errores de Klipper en ese intervalo | `klippy.log` | Alto: en Klipper estándar rota a medianoche y conserva 5 archivos anteriores, así que el del 25-09 probablemente ya no existe si la impresora siguió encendida |
| Comandos enviados por consola/API (`RESUME`, `PAUSE`) y respuestas de error | `/server/gcode_store` | Total si la impresora se reinició: se guarda en memoria |
| Estado final y horas del trabajo; otros trabajos con el mismo perfil | `/server/history/list` | Bajo: queda en la base de datos de Moonraker |
| Código de fin del archivo | final de `/server/files/gcodes/<archivo>` | Bajo mientras el archivo siga en la impresora |
| Macros `PAUSE`, `RESUME`, `END_PRINT` y límites de los ejes (`stepper_x.position_max`) | objeto `configfile` | Bajo |
