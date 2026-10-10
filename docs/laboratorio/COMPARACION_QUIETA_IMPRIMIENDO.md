# Descubrimiento con la impresora quieta, contra lo medido imprimiendo

Corrida del 2026-10-08, 17:27 a 17:35 (Colombia), con la .22 en `standby`, solo lectura (GET y una
suscripción de 60 s), con límite de 300 KB/s y los ocho pasos completos. Resultados crudos en
`descubrimiento_quieta/` (los logs, 128 MB, y la muestra del WebSocket no se versionan). La medición
anterior, con el trabajo 43 imprimiendo, está en `descubrimiento/`.

## Qué es igual (comparado archivo contra archivo)

| Archivo | Resultado |
|---|---|
| `objects.json` (117 objetos de Klipper) | idéntico |
| `configfile.json` (configuración completa) | idéntico |
| `macros.cfg` (71 macros) | idéntico |
| `printer_info.json`, `server_info.json` | idénticos |
| `webcams.json` | idéntico: Moonraker no publica ninguna cámara (`camaras: 0`) |

La configuración de la impresora no cambió entre una corrida y otra, y nada de lo que se asumió imprimiendo
(tamaño de cama, sensores, ventilador) depende del estado.

## Qué cambia con el estado

| Medida | Imprimiendo (trabajo 43) | Quieta (`standby`) |
|---|---|---|
| Duración de la medición | 300 s | 60 s |
| Mensajes | 1.491 (≈ 5 por segundo) | 300 (5 por segundo) |
| Intervalo mediano entre actualizaciones | 0,251 s | 0,251 s |
| Bytes por segundo | 4.165 | 2.432 |
| Extrapolación a 2 h | 30 MB | 17,5 MB |
| Objetos suscritos | 45 (sin macros) | 116 (con macros) |
| Campos que se actualizan | 128 | 74 |

- **No son comparables 1 a 1:** imprimiendo se suscribió a 45 objetos (sin las macros, para cargar menos);
  quieta, a 116. Aun así la cadencia de Moonraker es la misma (un mensaje cada 0,25 s). El volumen real de
  PrintWatch depende de lo que PrintWatch suscribe, no de estas cifras.
- **Los 54 campos que solo se mueven imprimiendo**, por objeto: `virtual_sdcard` (11), `gcode_move` (9),
  `toolhead` (8), `motion_report` (6, la posición real del cabezal), `fan_feedback` (3), `print_stats` (3),
  los tres drivers `tmc2208` (3 cada uno) y uno cada `display_status`, `idle_timeout`, `output_pin fan0`
  (el ventilador de capa), `extruder.power` y `heater_bed.power`. En `standby` no cambian.
- **Quieta sí cambian** (ruido de lectura): `temperature_sensor mcu_temp` (3,2 Hz), `heater_bed.temperature`
  (2,8 Hz) y `extruder.temperature` (1,6 Hz), más `toolhead.estimated_print_time` y las estadísticas de los
  MCU (0,33 Hz). La temperatura de la boquilla cambió menos que imprimiendo (3,1 Hz), como era de esperar.

## Logs de la impresora y el incidente del 25-09

- Se bajaron `klippy.log` (5,4 MB) y cinco rotados, y `moonraker.log` con dos rotados (128 MB en total).
  **Ninguno contiene `out of range`**: ni `Move out of range` ni nada parecido. Las fechas de los logs
  son las del reloj de la impresora (vuelve a 2020 en cada arranque) y no se pueden cruzar con el 25-09,
  así que no se puede decir si esos archivos cubren el incidente. Desde los logs de la impresora no se
  puede reconstruir el movimiento fuera de rango.
- `klippy.log` actual: sin `shutdown`; solo `BOX_ERROR_CLEAR` (macro de la caja, dos veces) y dos
  líneas `buf_len = 0x0` del arranque.
- Historial de Moonraker: 100 trabajos, uno con el archivo del incidente.

## Cámara

`/server/webcams/list` está vacío, así que el paso de cámaras no probó ninguna URL (solo toca lo que esa
lista publique). No se adivinó ningún puerto ni ruta.

## Qué queda sin responder

- Cómo accede el profesor a la cámara interna (ver `PREGUNTAS.md`, pregunta 1).
- Qué hizo exactamente la reanudación del 25-09: los logs de la impresora no lo guardan.
