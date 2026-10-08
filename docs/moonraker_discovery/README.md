# Descubrimiento de Moonraker/Klipper en la Creality Hi-3422

**Estado: plantilla sin verificar.** El descubrimiento todavía no se corrió contra la impresora real
(se preparó fuera del laboratorio). La tabla de abajo sale de la documentación de Klipper y Moonraker
y de lo que ya se midió en la Hi-3422 (marcado *medido*). Al correr el script se completa con lo que
la impresora devuelva de verdad; lo que siga marcado *sin verificar* no se debe tomar como hecho.

## Cómo correr el descubrimiento

Antes: VPN HotspotShield desconectada, sesión `wsl -- sleep infinity` abierta y
`curl.exe http://192.168.10.22:7125/printer/info` respondiendo.

1. **Corrida completa, con la impresora sin imprimir** (descarga logs y archivos):

   ```powershell
   backend\.venv\Scripts\python.exe backend\scripts\moonraker_discovery.py --url http://192.168.10.22:7125
   ```

2. **Medición del WebSocket durante una impresión** (no descarga nada; 10 minutos):

   ```powershell
   backend\.venv\Scripts\python.exe backend\scripts\moonraker_discovery.py --only-ws --ws-seconds 600
   ```

El script es de **solo lectura**: solo hace peticiones GET a una lista cerrada de rutas de consulta y,
por el WebSocket, solo usa métodos que leen estado (`printer.objects.list`, `.query`, `.subscribe`).
Cualquier otra ruta o método lanza un error antes de tocar la red (lo comprueban las pruebas de
`backend/tests/test_moonraker_discovery.py`). Si la impresora pide usuario o contraseña, se detiene
ahí sin intentar credenciales y guarda lo reunido. Se probó contra la impresora simulada
(`backend/scripts/mock_moonraker.py`).

Guarda primero lo que se pierde: el registro de la consola (`/server/gcode_store`, vive en memoria y
se borra al reiniciar) y los logs (rotan).

### Qué produce

| Archivo | Contenido |
|---|---|
| `resumen_descubrimiento.md` | Resumen automático: versiones, pasos, objetos y la frecuencia medida de cada campo |
| `objects.json`, `objects_status.json` | Lista de objetos de Klipper y el valor de cada uno al consultar |
| `configfile.json`, `macros.cfg`, `analisis_config.md` | Configuración: límites de ejes, malla, macros de pausa/reanudación/fin |
| `gcode_store.json/.txt` | Comandos de consola y respuestas que Moonraker tenga en memoria |
| `history_list.json`, `historial.txt` | Historial de impresiones |
| `logs/` | `klippy.log` y `moonraker.log`, más extractos alrededor del incidente del 25-09 |
| `gcode/`, `analisis_gcode.md` | Metadatos, inicio y final de los archivos impresos; movimientos fuera de rango |
| `webcams.json`, `webcam_probe.json`, `webcam/` | Cámara interna: URLs, imagen de prueba, resolución y cuadros por segundo |
| `system_info.json`, `proc_stats.json` | Equipo de la impresora (sin números de serie ni MAC) |
| `ws_medicion_<estado>.json` | Mensajes y bytes por segundo del WebSocket y actualizaciones por campo |

Los logs completos no se suben al repositorio (pesan y traen datos del equipo); se suben los extractos.

## Datos que expone (esperado)

Klipper manda las actualizaciones de una suscripción como mucho cada 250 ms y solo con los campos que
cambiaron, así que "~4 Hz" significa "mientras el valor cambia".

| Dato | Objeto / campo | Unidad | Frecuencia | ¿Confiable? | Uso en PrintWatch |
|---|---|---|---|---|---|
| Estado de la impresión | `print_stats.state` | — | al cambiar | Sí (*medido*) | Estado de la impresora y del trabajo (ya en uso) |
| Archivo | `print_stats.filename` | — | al cambiar | Sí (*medido*) | Nombre del trabajo (ya en uso) |
| Mensaje de error | `print_stats.message` | texto | al cambiar | Sí (*medido*); en la Hi llega como JSON con `code` (`key243`) | Bitácora |
| Capa actual | `virtual_sdcard.layer` (propio de Creality) | capa | al cambiar | Sí (*medido*) | Disparo de la captura (ya en uso) |
| Total de capas | `virtual_sdcard.layer_count` (propio de Creality) | capas | al empezar | Sí (*medido*) | Progreso |
| Altura de capa | `virtual_sdcard.cur_print_data.metadata.layer_height` | mm | al empezar | Sí (*medido*) | Z de cada capa |
| Capa según Klipper estándar | `print_stats.info.current_layer` | capa | — | No: siempre `null` (*medido*) | No se usa |
| Z reportada | `print_stats.z_pos` (propio de Creality) | mm | — | No: va con retraso (*medido*) | No se usa; Z = capa × altura |
| Posición comandada | `toolhead.position` [x, y, z, e] | mm | ~4 Hz | sin verificar | Telemetría |
| Posición real estimada | `motion_report.live_position` [x, y, z, e] | mm | ~4 Hz | sin verificar | Mapa de la cama y trayectoria |
| Velocidad real | `motion_report.live_velocity` | mm/s | ~4 Hz | sin verificar | Telemetría |
| Velocidad del extrusor | `motion_report.live_extruder_velocity` | mm/s de filamento | ~4 Hz | sin verificar | Fusión de sensores |
| Factor de velocidad | `gcode_move.speed_factor` | 1,0 = 100 % | al cambiar | sin verificar | Bitácora |
| Factor de flujo | `gcode_move.extrude_factor` | 1,0 = 100 % | al cambiar | sin verificar | Bitácora |
| Desfase de Z (babystepping) | `gcode_move.homing_origin[2]` | mm | al cambiar | sin verificar | Bitácora |
| Temperatura de la boquilla | `extruder.temperature`, `.target`, `.power` | °C, °C, 0–1 | ~4 Hz | sin verificar | Telemetría, bitácora, salud |
| Temperatura de la cama | `heater_bed.temperature`, `.target`, `.power` | °C, °C, 0–1 | ~4 Hz | sin verificar | Telemetría, bitácora, salud |
| Ventilador de capa | `fan.speed` | 0–1 | al cambiar | sin verificar | Telemetría, bitácora |
| Otros ventiladores | `heater_fan *`, `controller_fan *` | 0–1 | al cambiar | sin verificar | Salud |
| Sensores extra | `temperature_sensor *` | °C | ~4 Hz | sin verificar | Salud |
| Malla de la cama | `bed_mesh.probed_matrix`, `mesh_min`, `mesh_max` | mm | al calibrar | sin verificar | Mapa de la cama |
| Objetos de la placa | `exclude_object.objects`, `.current_object`, `.excluded_objects` | — | al cambiar | Depende de que el laminador los declare | Mapa de la cama, bitácora |
| Sensor de filamento | `filament_switch_sensor *.filament_detected` | sí/no | al cambiar | sin verificar | Bitácora |
| Progreso | `virtual_sdcard.progress` | 0–1 | ~4 Hz | sin verificar | Telemetría |
| Filamento usado | `print_stats.filament_used` | mm | ~4 Hz | sin verificar | Costo estimado |
| Duraciones | `print_stats.print_duration`, `.total_duration` | s | ~4 Hz | Sí (*medido*: `total_duration` coincidió con la base de datos a 0,2 s) | Telemetría |
| Carga del equipo | `system_stats`, `notify_proc_stat_update` | — | 1 Hz | sin verificar | Salud |
| Consola | `notify_gcode_response`, `/server/gcode_store` | texto | al ocurrir | sin verificar | Bitácora (comandos externos) |
| Historial | `/server/history/list`, `notify_history_changed` | — | al empezar/terminar | sin verificar | Contraste con nuestros trabajos |
| Cámara interna | `/server/webcams/list` | — | — | sin verificar | Segunda cámara |

### Lo que no sabemos todavía

- Qué objetos propios de Creality expone la Hi (por ejemplo el sistema de filamentos CFS o un sensor
  de cámara) y qué significan sus campos.
- Si el laminador declara los objetos (`EXCLUDE_OBJECT_DEFINE`); sin eso, `exclude_object` llega vacío.
- Si los ventiladores reportan RPM.
- Si la cámara interna existe y con qué resolución y cuadros por segundo.
- El volumen real de datos de una impresión, que define la frecuencia de muestreo de la Fase 1.

## Incidente de reanudación del 25-09-2026

Ver `incidente_reanudacion.md`. El script descarga y extrae la evidencia que falta (logs, consola,
historial, macros y final del archivo G-code).
