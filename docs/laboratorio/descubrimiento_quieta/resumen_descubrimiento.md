# Resumen automático del descubrimiento

Regenerado por `backend/scripts/moonraker_discovery.py` el 2026-10-08 22:35 UTC (2026-10-08 17:35 en Colombia). El análisis hecho a mano está en `README.md`.

- Impresora: `http://192.168.10.22:7125`, host `Creality Hi-3422`.
- Klipper `09faed31-dirty`; Moonraker `?`.
- Corrida completa: 2026-10-08T22:27:05+00:00 a 2026-10-08T22:35:42+00:00 (UTC).
- Reloj de la impresora menos reloj local: -213636672.1 s.

## Pasos

| Paso | Resultado | Detalle |
|---|---|---|
| consola_gcode_store | ok | {"lineas": 807, "desde_utc": "2020-01-01T00:00:56+00:00"} |
| logs | ok | {"logs": [{"archivo": "klippy.log", "tamano": 5355994, "modificado_utc": "2020-01-01T06:55:53+00:00", "descargado": 5356107, "cortado": false}, {"archivo": "... |
| historial | ok | {"trabajos": 100, "con_el_archivo_del_incidente": 1} |
| objetos | ok | {"objetos": 117, "no_reconocidos": ["custom_macro", "fan_feedback", "filament_rack", "box", "motor_control", "prtouch_v3", "steer"]} |
| configuracion | ok | {"macros": 71, "macros_relevantes": ["gcode_macro CANCEL_PRINT", "gcode_macro END_PRINT", "gcode_macro FIRST_FLOOR_PAUSE", "gcode_macro FIRST_FLOOR_PAUSE_POS... |
| archivos_gcode | ok | {"revisados": {"BOX FINAL lista pa imprimir_PETG_2h5m.gcode": true, "CAJA LISTA CARA ADALOVE LISTA PARA IMPRIMIR (1).stl_PETG_6h0m27s.gcode": true, "files-se... |
| camaras | ok | {"camaras": 0, "con_imagen": []} |
| sistema | ok | {} |
| medicion_websocket | ok | {"estado_impresora": "standby", "mensajes": 300, "bytes_por_segundo": 2432.0} |

## Objetos de Klipper (117)

Estándar de Klipper: `webhooks`, `configfile`, `mcu`, `mcu nozzle_mcu`, `mcu bed_mcu`, `mcu rpi`, `gcode_macro xyz_ready`, `gcode_macro ENABLE_ZDOWN`, `gcode_macro _IF_HOME_Z`, `gcode_macro _IF_MOVE_XY`, `gcode_macro _HOME_X`, `gcode_macro _HOME_Y`, `gcode_macro _HOME_Z`, `gcode_move`, `print_stats`, `virtual_sdcard`, `pause_resume`, `display_status`, `gcode_macro PRINTER_PARAM`, `gcode_macro STRUCTURE_PARAM`, `gcode_macro CANCEL_PRINT`, `gcode_macro MOTOR_CANCEL_PRINT`, `gcode_macro IF_NEED_HOME`, `gcode_macro PRINT_CALIBRATION`, `gcode_macro FIRST_FLOOR_PAUSE_POSITION`, `gcode_macro FIRST_FLOOR_RESUME`, `gcode_macro FIRST_FLOOR_PAUSE`, `gcode_macro RESPONSE_INFO`, `gcode_macro DO_COOLING`, `gcode_macro DO_CUT`, `gcode_macro IF_CUT_AND_COOLING`, `gcode_macro PAUSE`, `gcode_macro PAUSE_EXTERNAL`, `gcode_macro RESUME`, `gcode_macro RESUME_EXTERNAL_PROCESS`, `gcode_macro RESUME_EXTERNAL`, `gcode_macro M900`, `gcode_macro WAIT_TEMP_START`, `gcode_macro WAIT_TEMP_END`, `gcode_macro M204`, `gcode_macro M205`, `gcode_macro G29`, `gcode_macro CALIBRATE_CUT_POS`, `gcode_macro INPUTSHAPER`, `gcode_macro AUTOTUNE_SHAPERS`, `gcode_macro SET_PIN`, `gcode_macro M106`, `gcode_macro M107`, `gcode_macro COOLING_AFTER_LOAD_OR_QUIT_MATERIAL`, `gcode_macro LOAD_MATERIAL_END`, `gcode_macro LOAD_MATERIAL`, `gcode_macro QUIT_MATERIAL_END`, `gcode_macro QUIT_MATERIAL`, `gcode_macro EXTRUDE_BEFORE_CLEAR`, `gcode_macro TPU_EXTRUDE_BEFORE_CLEAR`, `gcode_macro M600`, `gcode_macro FINISH_INIT`, `gcode_macro PRINT_TEMP_SET`, `gcode_macro NOZCLEAR_START_PRINT`, `gcode_macro END_PRINT`, `gcode_macro START_PRINT`, `gcode_macro PRINT_PREPARED`, `gcode_macro PRINT_PREPARE_CLEAR`, `gcode_macro Qmode`, `gcode_macro Qmode_exit`, `gcode_macro Rmode`, `gcode_macro Rmode_exit`, `gcode_macro A_TriPress_STEP1`, `gcode_macro A_TriPress_STEP2`, `gcode_macro zLimit_state`, `gcode_macro MAINTENANCE_ITEM_PARAM`, `gcode_macro MAINTENANCE_ITEM`, `gcode_macro product_param`, `gcode_macro BOX_CHECK_MATERIAL`, `gcode_macro BOX_LOAD_MATERIAL_WITH_MATERIAL_END`, `gcode_macro BOX_LOAD_MATERIAL_WITH_MATERIAL`, `gcode_macro BOX_LOAD_MATERIAL_WITHOUT_MATERIAL`, `gcode_macro BOX_RETRUDE_MATERIAL_WITH_TNN`, `gcode_macro BOX_QUIT_MATERIAL_END`, `gcode_macro BOX_QUIT_MATERIAL`, `gcode_macro BOX_INFO_REFRESH`, `gcode_macro POP_FILAMENT_OUT`, `idle_timeout`, `heaters`, `temperature_sensor mcu_temp`, `tmc2208 stepper_z`, `tmc2208 stepper_z1`, `z_tilt`, `axis_twist_compensation`, `probe`, `tmc2208 extruder`, `heater_bed`, `output_pin fanp0`, `output_pin fan0`, `output_pin board_fan`, `heater_fan hotend_fan`, `bed_mesh`, `exclude_object`, `filament_switch_sensor filament_sensor`, `filament_switch_sensor filament_sensor_2`, `filament_switch_sensor filament_sensor_3`, `filament_switch_sensor filament_sensor_4`, `filament_switch_sensor filament_sensor_5`, `output_pin LED`, `motion_report`, `query_endstops`, `system_stats`, `manual_probe`, `toolhead`, `extruder`.

No reconocidos (posiblemente propios de Creality): `custom_macro`, `fan_feedback`, `filament_rack`, `box`, `motor_control`, `prtouch_v3`, `steer`.

## Medición del WebSocket con la impresora en `standby`

60.0 s el 2026-10-08T22:35:42+00:00: 300 mensajes, 2432.0 bytes/s. Intervalo mediano entre actualizaciones de estado: 0.251 s.

Mensajes por tipo: `notify_status_update` 239, `notify_proc_stat_update` 61.

## Campos (sin las macros)

| Campo | Valor al consultar | Hz en `standby` | Rango medido |
|---|---|---|---|
| `webhooks.state` | "ready" | 0 |  |
| `webhooks.state_message` | "Printer is ready" | 0 |  |
| `mcu.mcu_version` | "cf1eac2d-dirty-20250210_192534-ubuntu" | 0 |  |
| `mcu.mcu_build_versions` | "gcc: (15:9-2019-q4-0ubuntu1) 9.2.1 20191025 (release) [A... | 0 |  |
| `mcu.mcu_constants.ADC_MAX` | 4095 | 0 |  |
| `mcu.mcu_constants.CLOCK_FREQ` | 120000000 | 0 |  |
| `mcu.mcu_constants.MCU` | "gd32f303xe" | 0 |  |
| `mcu.mcu_constants.RECEIVE_WINDOW` | 192 | 0 |  |
| `mcu.mcu_constants.RESERVE_PINS_serial` | "PA2,PA3" | 0 |  |
| `mcu.mcu_constants.SERIAL_BAUD` | 230400 | 0 |  |
| `mcu.mcu_constants.STATS_SUMSQ_BASE` | 256 | 0 |  |
| `mcu.mcu_constants.STEPPER_BOTH_EDGE` | 1 | 0 |  |
| `mcu.mcu_constants.build_machine_uid` | "Feb 10 202519:25:28" | 0 |  |
| `mcu.last_stats.mcu_awake` | 0.001 | 0.333 | 0.001 a 0.001 |
| `mcu.last_stats.mcu_task_avg` | 8e-06 | 0.333 | 8e-06 a 8e-06 |
| `mcu.last_stats.mcu_task_stddev` | 4e-06 | 0.333 | 4e-06 a 4e-06 |
| `mcu.last_stats.bytes_write` | 43677056 | 0.333 | 43677564 a 43681104 |
| `mcu.last_stats.bytes_read` | 8764173 | 0.333 | 8765967 a 8778019 |
| `mcu.last_stats.bytes_retransmit` | 9 | 0.333 | 9 a 9 |
| `mcu.last_stats.bytes_invalid` | 0 | 0.333 | 0 a 0 |
| `mcu.last_stats.send_seq` | 801297 | 0.333 | 801339 a 801625 |
| `mcu.last_stats.receive_seq` | 801297 | 0.333 | 801339 a 801625 |
| `mcu.last_stats.retransmit_seq` | 2 | 0.333 | 2 a 2 |
| `mcu.last_stats.srtt` | 0.001 | 0.333 | 0.001 a 0.001 |
| `mcu.last_stats.rttvar` | 0 | 0.333 | 0 a 0 |
| `mcu.last_stats.rto` | 0.025 | 0.333 | 0.025 a 0.025 |
| `mcu.last_stats.ready_bytes` | 0 | 0.333 | 0 a 0 |
| `mcu.last_stats.stalled_bytes` | 0 | 0.333 | 0 a 0 |
| `mcu.last_stats.freq` | 119999077 | 0.333 | 119999077 a 119999082 |
| `mcu nozzle_mcu.mcu_version` | "23f337b2" | 0 |  |
| `mcu nozzle_mcu.mcu_build_versions` | "gcc: (15:9-2019-q4-0ubuntu1) 9.2.1 20191025 (release) [A... | 0 |  |
| `mcu nozzle_mcu.mcu_constants.ADC_MAX` | 4095 | 0 |  |
| `mcu nozzle_mcu.mcu_constants.CLOCK_FREQ` | 120000000 | 0 |  |
| `mcu nozzle_mcu.mcu_constants.MCU` | "gd32f303xb" | 0 |  |
| `mcu nozzle_mcu.mcu_constants.RECEIVE_WINDOW` | 192 | 0 |  |
| `mcu nozzle_mcu.mcu_constants.RESERVE_PINS_serial` | "PA2,PA3" | 0 |  |
| `mcu nozzle_mcu.mcu_constants.SERIAL_BAUD` | 230400 | 0 |  |
| `mcu nozzle_mcu.mcu_constants.STATS_SUMSQ_BASE` | 256 | 0 |  |
| `mcu nozzle_mcu.mcu_constants.STEPPER_BOTH_EDGE` | 1 | 0 |  |
| `mcu nozzle_mcu.mcu_constants.build_machine_uid` | "Sep  5 202416:56:45" | 0 |  |
| `mcu nozzle_mcu.last_stats.mcu_awake` | 0.003 | 0.333 | 0.002 a 0.003 |
| `mcu nozzle_mcu.last_stats.mcu_task_avg` | 6e-06 | 0.333 | 6e-06 a 6e-06 |
| `mcu nozzle_mcu.last_stats.mcu_task_stddev` | 5e-06 | 0.333 | 4e-06 a 5e-06 |
| `mcu nozzle_mcu.last_stats.bytes_write` | 24504095 | 0.333 | 24504195 a 24504767 |
| `mcu nozzle_mcu.last_stats.bytes_read` | 4767358 | 0.333 | 4768071 a 4772484 |
| `mcu nozzle_mcu.last_stats.bytes_retransmit` | 9 | 0.333 | 9 a 9 |
| `mcu nozzle_mcu.last_stats.bytes_invalid` | 0 | 0.333 | 0 a 0 |
| `mcu nozzle_mcu.last_stats.send_seq` | 459007 | 0.333 | 459022 a 459108 |
| `mcu nozzle_mcu.last_stats.receive_seq` | 459007 | 0.333 | 459022 a 459108 |
| `mcu nozzle_mcu.last_stats.retransmit_seq` | 2 | 0.333 | 2 a 2 |
| `mcu nozzle_mcu.last_stats.srtt` | 0.001 | 0.333 | 0.001 a 0.001 |
| `mcu nozzle_mcu.last_stats.rttvar` | 0 | 0.333 | 0 a 0 |
| `mcu nozzle_mcu.last_stats.rto` | 0.025 | 0.333 | 0.025 a 0.025 |
| `mcu nozzle_mcu.last_stats.ready_bytes` | 0 | 0.333 | 0 a 0 |
| `mcu nozzle_mcu.last_stats.stalled_bytes` | 0 | 0.333 | 0 a 0 |
| `mcu nozzle_mcu.last_stats.freq` | 120000504 | 0.333 | 120000508 a 120000520 |
| `mcu nozzle_mcu.last_stats.adj` | 120001450 | 0.333 | 120001375 a 120001595 |
| `mcu bed_mcu.mcu_version` | "54872883-dirty-20240605_163644-longer-virtual-machine" | 0 |  |
| `mcu bed_mcu.mcu_build_versions` | "gcc: (15:9-2019-q4-0ubuntu1) 9.2.1 20191025 (release) [A... | 0 |  |
| `mcu bed_mcu.mcu_constants.ADC_MAX` | 4095 | 0 |  |
| `mcu bed_mcu.mcu_constants.CLOCK_FREQ` | 72000000 | 0 |  |
| `mcu bed_mcu.mcu_constants.MCU` | "gd32e230x8" | 0 |  |
| `mcu bed_mcu.mcu_constants.RECEIVE_WINDOW` | 192 | 0 |  |
| `mcu bed_mcu.mcu_constants.RESERVE_PINS_serial` | "PA9,PA10" | 0 |  |
| `mcu bed_mcu.mcu_constants.SERIAL_BAUD` | 230400 | 0 |  |
| `mcu bed_mcu.mcu_constants.STATS_SUMSQ_BASE` | 256 | 0 |  |
| `mcu bed_mcu.mcu_constants.STEPPER_BOTH_EDGE` | 1 | 0 |  |
| `mcu bed_mcu.mcu_constants.build_machine_uid` | "Jun  5 202416:36:39" | 0 |  |
| `mcu bed_mcu.last_stats.mcu_awake` | 0 | 0.333 | 0 a 0 |
| `mcu bed_mcu.last_stats.mcu_task_avg` | 4e-06 | 0.333 | 4e-06 a 4e-06 |
| `mcu bed_mcu.last_stats.mcu_task_stddev` | 3e-06 | 0.333 | 3e-06 a 3e-06 |
| `mcu bed_mcu.last_stats.bytes_write` | 154895 | 0.333 | 154955 a 155303 |
| `mcu bed_mcu.last_stats.bytes_read` | 478524 | 0.333 | 478697 a 479777 |
| `mcu bed_mcu.last_stats.bytes_retransmit` | 9 | 0.333 | 9 a 9 |
| `mcu bed_mcu.last_stats.bytes_invalid` | 0 | 0.333 | 0 a 0 |
| `mcu bed_mcu.last_stats.send_seq` | 25796 | 0.333 | 25806 a 25864 |
| `mcu bed_mcu.last_stats.receive_seq` | 25796 | 0.333 | 25806 a 25864 |
| `mcu bed_mcu.last_stats.retransmit_seq` | 17 | 0.333 | 17 a 17 |
| `mcu bed_mcu.last_stats.srtt` | 0.001 | 0.333 | 0.001 a 0.001 |
| `mcu bed_mcu.last_stats.rttvar` | 0 | 0.333 | 0 a 0 |
| `mcu bed_mcu.last_stats.rto` | 0.025 | 0.333 | 0.025 a 0.025 |
| `mcu bed_mcu.last_stats.ready_bytes` | 0 | 0.333 | 0 a 0 |
| `mcu bed_mcu.last_stats.stalled_bytes` | 0 | 0.333 | 0 a 0 |
| `mcu bed_mcu.last_stats.freq` | 71833919 | 0.333 | 71833846 a 71834096 |
| `mcu bed_mcu.last_stats.adj` | 71834533 | 0.333 | 71832675 a 71836784 |
| `mcu rpi.mcu_version` | "43221f50-dirty-20240224_174812-ubuntu1804" | 0 |  |
| `mcu rpi.mcu_build_versions` | "gcc: (OpenWrt/CodeSourcery GCC 8.3.0 2021.08) 8.3.0 binu... | 0 |  |
| `mcu rpi.mcu_constants.ADC_MAX` | 4095 | 0 |  |
| `mcu rpi.mcu_constants.CLOCK_FREQ` | 50000000 | 0 |  |
| `mcu rpi.mcu_constants.MCU` | "linux" | 0 |  |
| `mcu rpi.mcu_constants.PCA9685_MAX` | 4096 | 0 |  |
| `mcu rpi.mcu_constants.PWM_MAX` | 32768 | 0 |  |
| `mcu rpi.mcu_constants.STATS_SUMSQ_BASE` | 256 | 0 |  |
| `mcu rpi.mcu_constants.build_machine_uid` | "Feb 24 202417:48:08" | 0 |  |
| `mcu rpi.last_stats.mcu_awake` | 0.001 | 0.333 | 0.001 a 0.001 |
| `mcu rpi.last_stats.mcu_task_avg` | 1e-05 | 0.333 | 1e-05 a 1.3e-05 |
| `mcu rpi.last_stats.mcu_task_stddev` | 1.4e-05 | 0.333 | 1.2e-05 a 2.9e-05 |
| `mcu rpi.last_stats.bytes_write` | 180025 | 0.333 | 180085 a 180433 |
| `mcu rpi.last_stats.bytes_read` | 494502 | 0.333 | 494675 a 495753 |
| `mcu rpi.last_stats.bytes_retransmit` | 0 | 0.333 | 0 a 0 |
| `mcu rpi.last_stats.bytes_invalid` | 0 | 0.333 | 0 a 0 |
| `mcu rpi.last_stats.send_seq` | 27801 | 0.333 | 27811 a 27869 |
| `mcu rpi.last_stats.receive_seq` | 27801 | 0.333 | 27811 a 27869 |
| `mcu rpi.last_stats.retransmit_seq` | 0 | 0.333 | 0 a 0 |
| `mcu rpi.last_stats.srtt` | 0 | 0.333 | 0 a 0.001 |
| `mcu rpi.last_stats.rttvar` | 0 | 0.333 | 0 a 0.001 |
| `mcu rpi.last_stats.rto` | 0.025 | 0.333 | 0.025 a 0.025 |
| `mcu rpi.last_stats.ready_bytes` | 0 | 0.333 | 0 a 0 |
| `mcu rpi.last_stats.stalled_bytes` | 0 | 0.333 | 0 a 0 |
| `mcu rpi.last_stats.freq` | 50000008 | 0.333 | 49999980 a 50000021 |
| `mcu rpi.last_stats.adj` | 50000664 | 0.333 | 50000262 a 50000525 |
| `gcode_move.speed_factor` | 1 | 0 |  |
| `gcode_move.speed` | 3000 | 0 |  |
| `gcode_move.extrude_factor` | 1 | 0 |  |
| `gcode_move.absolute_coordinates` | true | 0 |  |
| `gcode_move.absolute_extrude` | false | 0 |  |
| `gcode_move.homing_origin[0]` | 0 | 0 |  |
| `gcode_move.homing_origin[1]` | 0 | 0 |  |
| `gcode_move.homing_origin[2]` | 0 | 0 |  |
| `gcode_move.homing_origin[3]` | 0 | 0 |  |
| `gcode_move.position[0]` | -5 | 0 |  |
| `gcode_move.position[1]` | 130 | 0 |  |
| `gcode_move.position[2]` | 10.1 | 0 |  |
| `gcode_move.position[3]` | 6.86e+04 | 0 |  |
| `gcode_move.gcode_position[0]` | -5 | 0 |  |
| `gcode_move.gcode_position[1]` | 130 | 0 |  |
| `gcode_move.gcode_position[2]` | 10.1 | 0 |  |
| `gcode_move.gcode_position[3]` | 179.3 | 0 |  |
| `print_stats.filename` | "" | 0 |  |
| `print_stats.total_duration` | 0 | 0 |  |
| `print_stats.print_duration` | 0 | 0 |  |
| `print_stats.filament_used` | 0 | 0 |  |
| `print_stats.state` | "standby" | 0 |  |
| `print_stats.message` | "" | 0 |  |
| `print_stats.info.total_layer` | null | 0 |  |
| `print_stats.info.current_layer` | null | 0 |  |
| `print_stats.power_loss` | 0 | 0 |  |
| `print_stats.z_pos` | 10.1 | 0 |  |
| `virtual_sdcard.file_path` | null | 0 |  |
| `virtual_sdcard.progress` | 0 | 0 |  |
| `virtual_sdcard.is_active` | false | 0 |  |
| `virtual_sdcard.file_position` | 0 | 0 |  |
| `virtual_sdcard.file_size` | 0 | 0 |  |
| `virtual_sdcard.first_layer_stop` | false | 0 |  |
| `virtual_sdcard.layer` | 0 | 0 |  |
| `virtual_sdcard.layer_count` | 0 | 0 |  |
| `virtual_sdcard.run_dis` | 0 | 0 |  |
| `virtual_sdcard.klipper_capture` | false | 0 |  |
| `virtual_sdcard.cur_print_data.end_time` | 1.578e+09 | 0 |  |
| `virtual_sdcard.cur_print_data.filament_used` | 6.82e+04 | 0 |  |
| `virtual_sdcard.cur_print_data.filename` | "CAJA LISTA CARA ADALOVE LISTA PARA IMPRIMIR (1).stl_PETG... | 0 |  |
| `virtual_sdcard.cur_print_data.metadata` | {"size": 10321936, "modified": 1577837446.6100004, "uuid"... | 0 |  |
| `virtual_sdcard.cur_print_data.print_duration` | 2.166e+04 | 0 |  |
| `virtual_sdcard.cur_print_data.start_time` | 1.578e+09 | 0 |  |
| `virtual_sdcard.cur_print_data.status` | "completed" | 0 |  |
| `virtual_sdcard.cur_print_data.total_duration` | 2.172e+04 | 0 |  |
| `pause_resume.is_paused` | false | 0 |  |
| `pause_resume.resume_err` | false | 0 |  |
| `display_status.progress` | 0 | 0 |  |
| `display_status.message` | null | 0 |  |
| `custom_macro.leveling_calibration` | 0 | 0 |  |
| `custom_macro.default_extruder_temp` | 240 | 0 |  |
| `custom_macro.default_bed_temp` | 50 | 0 |  |
| `custom_macro.g28_ext_temp` | 140 | 0 |  |
| `custom_macro.qmode_flag` | 0 | 0 |  |
| `fan_feedback.fan0_speed` | 0 | 0 |  |
| `fan_feedback.fan1_speed` | 0 | 0 |  |
| `fan_feedback.fan2_speed` | 0 | 0 |  |
| `fan_feedback.fan3_speed` | 0 | 0 |  |
| `fan_feedback.fan4_speed` | 0 | 0 |  |
| `filament_rack.vender` | "Creality" | 0 |  |
| `filament_rack.color_value` | "01B04AE" | 0 |  |
| `filament_rack.material_type` | "006001" | 0 |  |
| `box.filament` | 1 | 0 |  |
| `box.state` | "disconnect" | 0 |  |
| `box.auto_refill` | 1 | 0 |  |
| `box.enable` | 1 | 0 |  |
| `box.filament_useup` | 1 | 0 |  |
| `box.same_material` | [] | 0 |  |
| `box.map.T1A` | "T1A" | 0 |  |
| `box.map.T1B` | "T1B" | 0 |  |
| `box.map.T1C` | "T1C" | 0 |  |
| `box.map.T1D` | "T1D" | 0 |  |
| `box.map.T2A` | "T2A" | 0 |  |
| `box.map.T2B` | "T2B" | 0 |  |
| `box.map.T2C` | "T2C" | 0 |  |
| `box.map.T2D` | "T2D" | 0 |  |
| `box.map.T3A` | "T3A" | 0 |  |
| `box.map.T3B` | "T3B" | 0 |  |
| `box.map.T3C` | "T3C" | 0 |  |
| `box.map.T3D` | "T3D" | 0 |  |
| `box.map.T4A` | "T4A" | 0 |  |
| `box.map.T4B` | "T4B" | 0 |  |
| `box.map.T4C` | "T4C" | 0 |  |
| `box.map.T4D` | "T4D" | 0 |  |
| `box.T1.state` | "None" | 0 |  |
| `box.T1.filament` | "None" | 0 |  |
| `box.T1.temperature` | "None" | 0 |  |
| `box.T1.dry_and_humidity` | "None" | 0 |  |
| `box.T1.filament_detected` | "None" | 0 |  |
| `box.T1.measuring_wheel` | "None" | 0 |  |
| `box.T1.version` | "-1" | 0 |  |
| `box.T1.sn` | "-1" | 0 |  |
| `box.T1.mode` | "-1" | 0 |  |
| `box.T1.vender` | ["-1", "-1", "-1", "-1"] | 0 |  |
| `box.T1.remain_len` | ["-1", "-1", "-1", "-1"] | 0 |  |
| `box.T1.color_value` | ["-1", "-1", "-1", "-1"] | 0 |  |
| `box.T1.material_type` | ["-1", "-1", "-1", "-1"] | 0 |  |
| `box.T1.uuid` | "None" | 0 |  |
| `box.T1.change_color_num[0]` | -1 | 0 |  |
| `box.T1.change_color_num[1]` | -1 | 0 |  |
| `box.T1.change_color_num[2]` | -1 | 0 |  |
| `box.T1.change_color_num[3]` | -1 | 0 |  |
| `box.T2.state` | "None" | 0 |  |
| `box.T2.filament` | "None" | 0 |  |
| `box.T2.temperature` | "None" | 0 |  |
| `box.T2.dry_and_humidity` | "None" | 0 |  |
| `box.T2.filament_detected` | "None" | 0 |  |
| `box.T2.measuring_wheel` | "None" | 0 |  |
| `box.T2.version` | "-1" | 0 |  |
| `box.T2.sn` | "-1" | 0 |  |
| `box.T2.mode` | "-1" | 0 |  |
| `box.T2.vender` | ["-1", "-1", "-1", "-1"] | 0 |  |
| `box.T2.remain_len` | ["-1", "-1", "-1", "-1"] | 0 |  |
| `box.T2.color_value` | ["-1", "-1", "-1", "-1"] | 0 |  |
| `box.T2.material_type` | ["-1", "-1", "-1", "-1"] | 0 |  |
| `box.T2.uuid` | "None" | 0 |  |
| `box.T2.change_color_num[0]` | -1 | 0 |  |
| `box.T2.change_color_num[1]` | -1 | 0 |  |
| `box.T2.change_color_num[2]` | -1 | 0 |  |
| `box.T2.change_color_num[3]` | -1 | 0 |  |
| `box.T3.state` | "None" | 0 |  |
| `box.T3.filament` | "None" | 0 |  |
| `box.T3.temperature` | "None" | 0 |  |
| `box.T3.dry_and_humidity` | "None" | 0 |  |
| `box.T3.filament_detected` | "None" | 0 |  |
| `box.T3.measuring_wheel` | "None" | 0 |  |
| `box.T3.version` | "-1" | 0 |  |
| `box.T3.sn` | "-1" | 0 |  |
| `box.T3.mode` | "-1" | 0 |  |
| `box.T3.vender` | ["-1", "-1", "-1", "-1"] | 0 |  |
| `box.T3.remain_len` | ["-1", "-1", "-1", "-1"] | 0 |  |
| `box.T3.color_value` | ["-1", "-1", "-1", "-1"] | 0 |  |
| `box.T3.material_type` | ["-1", "-1", "-1", "-1"] | 0 |  |
| `box.T3.uuid` | "None" | 0 |  |
| `box.T3.change_color_num[0]` | -1 | 0 |  |
| `box.T3.change_color_num[1]` | -1 | 0 |  |
| `box.T3.change_color_num[2]` | -1 | 0 |  |
| `box.T3.change_color_num[3]` | -1 | 0 |  |
| `box.T4.state` | "None" | 0 |  |
| `box.T4.filament` | "None" | 0 |  |
| `box.T4.temperature` | "None" | 0 |  |
| `box.T4.dry_and_humidity` | "None" | 0 |  |
| `box.T4.filament_detected` | "None" | 0 |  |
| `box.T4.measuring_wheel` | "None" | 0 |  |
| `box.T4.version` | "-1" | 0 |  |
| `box.T4.sn` | "-1" | 0 |  |
| `box.T4.mode` | "-1" | 0 |  |
| `box.T4.vender` | ["-1", "-1", "-1", "-1"] | 0 |  |
| `box.T4.remain_len` | ["-1", "-1", "-1", "-1"] | 0 |  |
| `box.T4.color_value` | ["-1", "-1", "-1", "-1"] | 0 |  |
| `box.T4.material_type` | ["-1", "-1", "-1", "-1"] | 0 |  |
| `box.T4.uuid` | "None" | 0 |  |
| `box.T4.change_color_num[0]` | -1 | 0 |  |
| `box.T4.change_color_num[1]` | -1 | 0 |  |
| `box.T4.change_color_num[2]` | -1 | 0 |  |
| `box.T4.change_color_num[3]` | -1 | 0 |  |
| `box.cut_state` | 1 | 0 |  |
| `motor_control.motor_ready` | true | 0 |  |
| `motor_control.is_homing` | false | 0 |  |
| `motor_control.cut.state` | true | 0 |  |
| `motor_control.cut.pos_x` | 279.6 | 0 |  |
| `idle_timeout.state` | "Ready" | 0 |  |
| `idle_timeout.printing_time` | 0 | 0 |  |
| `heaters.available_heaters` | ["heater_bed", "extruder"] | 0 |  |
| `heaters.available_sensors` | ["temperature_sensor mcu_temp", "heater_bed", "extruder"] | 0 |  |
| `heaters.extruder_temperature_wait` | false | 0 |  |
| `heaters.bed_temperature_wait` | false | 0 |  |
| `temperature_sensor mcu_temp.temperature` | 45.55 | 3.182 | 45.23 a 46.27 |
| `temperature_sensor mcu_temp.measured_min_temp` | 33.88 | 0 |  |
| `temperature_sensor mcu_temp.measured_max_temp` | 58.21 | 0 |  |
| `tmc2208 stepper_z.mcu_phase_offset` | 31 | 0 |  |
| `tmc2208 stepper_z.phase_offset_position` | 464.4 | 0 |  |
| `tmc2208 stepper_z.run_current` | 0.4972 | 0 |  |
| `tmc2208 stepper_z.hold_current` | 0.4972 | 0 |  |
| `tmc2208 stepper_z.drv_status.cs_actual` | 14 | 0 |  |
| `tmc2208 stepper_z.drv_status.stealth` | 1 | 0 |  |
| `tmc2208 stepper_z.drv_status.stst` | 1 | 0 |  |
| `tmc2208 stepper_z1.mcu_phase_offset` | 2 | 0 |  |
| `tmc2208 stepper_z1.phase_offset_position` | 464.9 | 0 |  |
| `tmc2208 stepper_z1.run_current` | 0.4972 | 0 |  |
| `tmc2208 stepper_z1.hold_current` | 0.4972 | 0 |  |
| `tmc2208 stepper_z1.drv_status.cs_actual` | 14 | 0 |  |
| `tmc2208 stepper_z1.drv_status.stealth` | 1 | 0 |  |
| `tmc2208 stepper_z1.drv_status.stst` | 1 | 0 |  |
| `z_tilt.applied` | false | 0 |  |
| `axis_twist_compensation.on_turb` | false | 0 |  |
| `axis_twist_compensation.pres_state` | true | 0 |  |
| `axis_twist_compensation.pres_data` | [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0] | 0 |  |
| `probe.last_query` | false | 0 |  |
| `probe.last_z_result` | -0.0375 | 0 |  |
| `probe.z_offset` | 0 | 0 |  |
| `prtouch_v3.on_turb` | false | 0 |  |
| `prtouch_v3.pres_state` | true | 0 |  |
| `prtouch_v3.pres_data` | [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0] | 0 |  |
| `tmc2208 extruder.mcu_phase_offset` | 63 | 0 |  |
| `tmc2208 extruder.phase_offset_position` | 0.1358 | 0 |  |
| `tmc2208 extruder.run_current` | 0.3729 | 0 |  |
| `tmc2208 extruder.hold_current` | 0.3729 | 0 |  |
| `tmc2208 extruder.drv_status` | null | 0 |  |
| `heater_bed.temperature` | 33.37 | 2.849 | 33.02 a 33.58 |
| `heater_bed.target` | 0 | 0 |  |
| `heater_bed.power` | 0 | 0 |  |
| `output_pin fanp0.value` | 0 | 0 |  |
| `output_pin fan0.value` | 0 | 0 |  |
| `output_pin board_fan.value` | 0 | 0 |  |
| `heater_fan hotend_fan.speed` | 0 | 0 |  |
| `heater_fan hotend_fan.rpm` | null | 0 |  |
| `bed_mesh.profile_name` | "" | 0 |  |
| `bed_mesh.mesh_min[0]` | 0 | 0 |  |
| `bed_mesh.mesh_min[1]` | 0 | 0 |  |
| `bed_mesh.mesh_max[0]` | 0 | 0 |  |
| `bed_mesh.mesh_max[1]` | 0 | 0 |  |
| `bed_mesh.probed_matrix` | [[]] | 0 |  |
| `bed_mesh.mesh_matrix` | [[]] | 0 |  |
| `bed_mesh.profiles.default` | {"points": [[0.101, 0.085, 0.092, 0.108, 0.055, 0.052, 0.... | 0 |  |
| `exclude_object.objects` | [] | 0 |  |
| `exclude_object.excluded_objects` | [] | 0 |  |
| `exclude_object.current_object` | null | 0 |  |
| `filament_switch_sensor filament_sensor.filament_detected` | false | 0 |  |
| `filament_switch_sensor filament_sensor.enabled` | true | 0 |  |
| `filament_switch_sensor filament_sensor_2.filament_detected` | true | 0 |  |
| `filament_switch_sensor filament_sensor_2.enabled` | true | 0 |  |
| `filament_switch_sensor filament_sensor_3.filament_detected` | false | 0 |  |
| `filament_switch_sensor filament_sensor_3.enabled` | true | 0 |  |
| `filament_switch_sensor filament_sensor_4.filament_detected` | false | 0 |  |
| `filament_switch_sensor filament_sensor_4.enabled` | true | 0 |  |
| `filament_switch_sensor filament_sensor_5.filament_detected` | false | 0 |  |
| `filament_switch_sensor filament_sensor_5.enabled` | true | 0 |  |
| `output_pin LED.value` | 1 | 0 |  |
| `steer.state` | false | 0 |  |
| `steer.enable` | false | 0 |  |
| `motion_report.live_position[0]` | -5 | 0 |  |
| `motion_report.live_position[1]` | 130 | 0 |  |
| `motion_report.live_position[2]` | 10.1 | 0 |  |
| `motion_report.live_position[3]` | 6.86e+04 | 0 |  |
| `motion_report.live_velocity` | 0 | 0 |  |
| `motion_report.live_extruder_velocity` | 0 | 0 |  |
| `motion_report.steppers` | ["extruder", "stepper_x", "stepper_y", "stepper_z", "step... | 0 |  |
| `motion_report.trapq` | ["extruder", "toolhead"] | 0 |  |
| `system_stats.sysload` | 0.28 | 0.2 | 0.36 a 0.83 |
| `system_stats.cputime` | 5076 | 0.333 | 5077 a 5085 |
| `system_stats.memavail` | 364468 | 0.317 | 363304 a 364432 |
| `manual_probe.is_active` | false | 0 |  |
| `manual_probe.z_position` | null | 0 |  |
| `manual_probe.z_position_lower` | null | 0 |  |
| `manual_probe.z_position_upper` | null | 0 |  |
| `toolhead.homed_axes` | "xyz" | 0 |  |
| `toolhead.axis_minimum[0]` | -19 | 0 |  |
| `toolhead.axis_minimum[1]` | -7 | 0 |  |
| `toolhead.axis_minimum[2]` | -5 | 0 |  |
| `toolhead.axis_minimum[3]` | 0 | 0 |  |
| `toolhead.axis_maximum[0]` | 285 | 0 |  |
| `toolhead.axis_maximum[1]` | 273 | 0 |  |
| `toolhead.axis_maximum[2]` | 310 | 0 |  |
| `toolhead.axis_maximum[3]` | 0 | 0 |  |
| `toolhead.print_time` | 2.38e+04 | 0 |  |
| `toolhead.stalls` | 0 | 0 |  |
| `toolhead.estimated_print_time` | 2.537e+04 | 3.982 | 2.538e+04 a 2.544e+04 |
| `toolhead.extruder` | "extruder" | 0 |  |
| `toolhead.position[0]` | -5 | 0 |  |
| `toolhead.position[1]` | 130 | 0 |  |
| `toolhead.position[2]` | 10.1 | 0 |  |
| `toolhead.position[3]` | 6.86e+04 | 0 |  |
| `toolhead.max_velocity` | 300 | 0 |  |
| `toolhead.max_accel` | 5000 | 0 |  |
| `toolhead.max_accel_to_decel` | 3e+04 | 0 |  |
| `toolhead.square_corner_velocity` | 12 | 0 |  |
| `toolhead.G29_flag` | false | 0 |  |
| `extruder.temperature` | 34.29 | 1.616 | 34.11 a 34.31 |
| `extruder.target` | 0 | 0 |  |
| `extruder.power` | 0 | 0 |  |
| `extruder.can_extrude` | false | 0 |  |
| `extruder.nozzle_diameter` | 0.4 | 0 |  |
| `extruder.extrude_below_min_temp_err_is_report` | false | 0 |  |
| `extruder.pressure_advance` | 0.072 | 0 |  |
| `extruder.smooth_time` | 0.04 | 0 |  |
