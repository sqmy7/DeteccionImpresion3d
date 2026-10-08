# Resumen automático del descubrimiento

Regenerado por `backend/scripts/moonraker_discovery.py` el 2026-10-08 19:32 UTC (2026-10-08 14:32 en Colombia). El análisis hecho a mano está en `README.md`.

- Impresora: `http://192.168.10.22:7125`, host `Creality Hi-3422`.
- Klipper `09faed31-dirty`; Moonraker `?`.
- Corrida completa: 2026-10-08T19:24:15+00:00 a 2026-10-08T19:32:45+00:00 (UTC).
- Reloj de la impresora menos reloj local: -213636671.4 s.

## Pasos

| Paso | Resultado | Detalle |
|---|---|---|
| logs | ok | {"logs": [{"archivo": "klippy.log", "tamano": 22050769, "modificado_utc": "2020-01-01T03:53:04+00:00", "descargado": 22050769, "cortado": false}, {"archivo":... |

## Objetos de Klipper (117)

Estándar de Klipper: `webhooks`, `configfile`, `mcu`, `mcu nozzle_mcu`, `mcu bed_mcu`, `mcu rpi`, `gcode_macro xyz_ready`, `gcode_macro ENABLE_ZDOWN`, `gcode_macro _IF_HOME_Z`, `gcode_macro _IF_MOVE_XY`, `gcode_macro _HOME_X`, `gcode_macro _HOME_Y`, `gcode_macro _HOME_Z`, `gcode_move`, `print_stats`, `virtual_sdcard`, `pause_resume`, `display_status`, `gcode_macro PRINTER_PARAM`, `gcode_macro STRUCTURE_PARAM`, `gcode_macro CANCEL_PRINT`, `gcode_macro MOTOR_CANCEL_PRINT`, `gcode_macro IF_NEED_HOME`, `gcode_macro PRINT_CALIBRATION`, `gcode_macro FIRST_FLOOR_PAUSE_POSITION`, `gcode_macro FIRST_FLOOR_RESUME`, `gcode_macro FIRST_FLOOR_PAUSE`, `gcode_macro RESPONSE_INFO`, `gcode_macro DO_COOLING`, `gcode_macro DO_CUT`, `gcode_macro IF_CUT_AND_COOLING`, `gcode_macro PAUSE`, `gcode_macro PAUSE_EXTERNAL`, `gcode_macro RESUME`, `gcode_macro RESUME_EXTERNAL_PROCESS`, `gcode_macro RESUME_EXTERNAL`, `gcode_macro M900`, `gcode_macro WAIT_TEMP_START`, `gcode_macro WAIT_TEMP_END`, `gcode_macro M204`, `gcode_macro M205`, `gcode_macro G29`, `gcode_macro CALIBRATE_CUT_POS`, `gcode_macro INPUTSHAPER`, `gcode_macro AUTOTUNE_SHAPERS`, `gcode_macro SET_PIN`, `gcode_macro M106`, `gcode_macro M107`, `gcode_macro COOLING_AFTER_LOAD_OR_QUIT_MATERIAL`, `gcode_macro LOAD_MATERIAL_END`, `gcode_macro LOAD_MATERIAL`, `gcode_macro QUIT_MATERIAL_END`, `gcode_macro QUIT_MATERIAL`, `gcode_macro EXTRUDE_BEFORE_CLEAR`, `gcode_macro TPU_EXTRUDE_BEFORE_CLEAR`, `gcode_macro M600`, `gcode_macro FINISH_INIT`, `gcode_macro PRINT_TEMP_SET`, `gcode_macro NOZCLEAR_START_PRINT`, `gcode_macro END_PRINT`, `gcode_macro START_PRINT`, `gcode_macro PRINT_PREPARED`, `gcode_macro PRINT_PREPARE_CLEAR`, `gcode_macro Qmode`, `gcode_macro Qmode_exit`, `gcode_macro Rmode`, `gcode_macro Rmode_exit`, `gcode_macro A_TriPress_STEP1`, `gcode_macro A_TriPress_STEP2`, `gcode_macro zLimit_state`, `gcode_macro MAINTENANCE_ITEM_PARAM`, `gcode_macro MAINTENANCE_ITEM`, `gcode_macro product_param`, `gcode_macro BOX_CHECK_MATERIAL`, `gcode_macro BOX_LOAD_MATERIAL_WITH_MATERIAL_END`, `gcode_macro BOX_LOAD_MATERIAL_WITH_MATERIAL`, `gcode_macro BOX_LOAD_MATERIAL_WITHOUT_MATERIAL`, `gcode_macro BOX_RETRUDE_MATERIAL_WITH_TNN`, `gcode_macro BOX_QUIT_MATERIAL_END`, `gcode_macro BOX_QUIT_MATERIAL`, `gcode_macro BOX_INFO_REFRESH`, `gcode_macro POP_FILAMENT_OUT`, `idle_timeout`, `heaters`, `temperature_sensor mcu_temp`, `tmc2208 stepper_z`, `tmc2208 stepper_z1`, `z_tilt`, `axis_twist_compensation`, `probe`, `tmc2208 extruder`, `heater_bed`, `output_pin fanp0`, `output_pin fan0`, `output_pin board_fan`, `heater_fan hotend_fan`, `bed_mesh`, `exclude_object`, `filament_switch_sensor filament_sensor`, `filament_switch_sensor filament_sensor_2`, `filament_switch_sensor filament_sensor_3`, `filament_switch_sensor filament_sensor_4`, `filament_switch_sensor filament_sensor_5`, `output_pin LED`, `motion_report`, `query_endstops`, `system_stats`, `manual_probe`, `toolhead`, `extruder`.

No reconocidos (posiblemente propios de Creality): `custom_macro`, `fan_feedback`, `filament_rack`, `box`, `motor_control`, `prtouch_v3`, `steer`.

## Medición del WebSocket con la impresora en `printing`

300.0 s el 2026-10-08T19:23:29+00:00: 1491 mensajes, 4165.2 bytes/s (en una impresión de 2 h serían ~30.0 MB). Intervalo mediano entre actualizaciones de estado: 0.251 s.

Mensajes por tipo: `notify_status_update` 1191, `notify_proc_stat_update` 300.

## Campos (sin las macros)

| Campo | Valor al consultar | Hz en `printing` | Rango medido |
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
| `mcu.last_stats.mcu_awake` | 0.004 | 0.333 | 0.002 a 0.011 |
| `mcu.last_stats.mcu_task_avg` | 1.8e-05 | 0.333 | 1.3e-05 a 2.4e-05 |
| `mcu.last_stats.mcu_task_stddev` | 1.3e-05 | 0.333 | 1e-05 a 1.3e-05 |
| `mcu.last_stats.bytes_write` | 25400959 | 0.333 | 25593411 a 26172658 |
| `mcu.last_stats.bytes_read` | 4880003 | 0.333 | 4915131 a 5022321 |
| `mcu.last_stats.bytes_retransmit` | 9 | 0.333 | 9 a 9 |
| `mcu.last_stats.bytes_invalid` | 0 | 0.333 | 0 a 0 |
| `mcu.last_stats.send_seq` | 462588 | 0.333 | 466046 a 476464 |
| `mcu.last_stats.receive_seq` | 462588 | 0.333 | 466046 a 476464 |
| `mcu.last_stats.retransmit_seq` | 2 | 0.333 | 2 a 2 |
| `mcu.last_stats.srtt` | 0.001 | 0.333 | 0.001 a 0.004 |
| `mcu.last_stats.rttvar` | 0 | 0.333 | 0 a 0.002 |
| `mcu.last_stats.rto` | 0.025 | 0.333 | 0.025 a 0.025 |
| `mcu.last_stats.ready_bytes` | 0 | 0.333 | 0 a 2153 |
| `mcu.last_stats.stalled_bytes` | 0 | 0.333 | 0 a 0 |
| `mcu.last_stats.freq` | 119999006 | 0.333 | 119998919 a 119999040 |
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
| `mcu nozzle_mcu.last_stats.mcu_awake` | 0.004 | 0.333 | 0.002 a 0.009 |
| `mcu nozzle_mcu.last_stats.mcu_task_avg` | 1.3e-05 | 0.333 | 1e-05 a 2e-05 |
| `mcu nozzle_mcu.last_stats.mcu_task_stddev` | 1.3e-05 | 0.333 | 1e-05 a 1.4e-05 |
| `mcu nozzle_mcu.last_stats.bytes_write` | 12956514 | 0.333 | 13096082 a 13516774 |
| `mcu nozzle_mcu.last_stats.bytes_read` | 2571189 | 0.333 | 2593433 a 2660945 |
| `mcu nozzle_mcu.last_stats.bytes_retransmit` | 9 | 0.333 | 9 a 9 |
| `mcu nozzle_mcu.last_stats.bytes_invalid` | 0 | 0.333 | 0 a 0 |
| `mcu nozzle_mcu.last_stats.send_seq` | 243310 | 0.333 | 245838 a 253415 |
| `mcu nozzle_mcu.last_stats.receive_seq` | 243310 | 0.333 | 245838 a 253415 |
| `mcu nozzle_mcu.last_stats.retransmit_seq` | 2 | 0.333 | 2 a 2 |
| `mcu nozzle_mcu.last_stats.srtt` | 0.001 | 0.333 | 0.001 a 0.003 |
| `mcu nozzle_mcu.last_stats.rttvar` | 0 | 0.333 | 0 a 0.002 |
| `mcu nozzle_mcu.last_stats.rto` | 0.025 | 0.333 | 0.025 a 0.025 |
| `mcu nozzle_mcu.last_stats.ready_bytes` | 51 | 0.333 | 0 a 1526 |
| `mcu nozzle_mcu.last_stats.stalled_bytes` | 9 | 0.333 | 0 a 27 |
| `mcu nozzle_mcu.last_stats.freq` | 120000421 | 0.333 | 120000342 a 120000520 |
| `mcu nozzle_mcu.last_stats.adj` | 120001587 | 0.333 | 120000940 a 120002416 |
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
| `mcu bed_mcu.last_stats.mcu_awake` | 0 | 0.333 | 0 a 0.001 |
| `mcu bed_mcu.last_stats.mcu_task_avg` | 4e-06 | 0.333 | 4e-06 a 1.2e-05 |
| `mcu bed_mcu.last_stats.mcu_task_stddev` | 3e-06 | 0.333 | 3e-06 a 0.001946 |
| `mcu bed_mcu.last_stats.bytes_write` | 82727 | 0.333 | 83315 a 85121 |
| `mcu bed_mcu.last_stats.bytes_read` | 256292 | 0.333 | 258103 a 263656 |
| `mcu bed_mcu.last_stats.bytes_retransmit` | 9 | 0.333 | 9 a 9 |
| `mcu bed_mcu.last_stats.bytes_invalid` | 0 | 0.333 | 0 a 0 |
| `mcu bed_mcu.last_stats.send_seq` | 13768 | 0.333 | 13866 a 14167 |
| `mcu bed_mcu.last_stats.receive_seq` | 13768 | 0.333 | 13866 a 14167 |
| `mcu bed_mcu.last_stats.retransmit_seq` | 17 | 0.333 | 17 a 17 |
| `mcu bed_mcu.last_stats.srtt` | 0.001 | 0.333 | 0.001 a 0.001 |
| `mcu bed_mcu.last_stats.rttvar` | 0 | 0.333 | 0 a 0.001 |
| `mcu bed_mcu.last_stats.rto` | 0.025 | 0.333 | 0.025 a 0.025 |
| `mcu bed_mcu.last_stats.ready_bytes` | 0 | 0.333 | 0 a 0 |
| `mcu bed_mcu.last_stats.stalled_bytes` | 0 | 0.333 | 0 a 0 |
| `mcu bed_mcu.last_stats.freq` | 71833978 | 0.333 | 71833782 a 71834123 |
| `mcu bed_mcu.last_stats.adj` | 71834436 | 0.333 | 71832761 a 71836259 |
| `mcu rpi.mcu_version` | "43221f50-dirty-20240224_174812-ubuntu1804" | 0 |  |
| `mcu rpi.mcu_build_versions` | "gcc: (OpenWrt/CodeSourcery GCC 8.3.0 2021.08) 8.3.0 binu... | 0 |  |
| `mcu rpi.mcu_constants.ADC_MAX` | 4095 | 0 |  |
| `mcu rpi.mcu_constants.CLOCK_FREQ` | 50000000 | 0 |  |
| `mcu rpi.mcu_constants.MCU` | "linux" | 0 |  |
| `mcu rpi.mcu_constants.PCA9685_MAX` | 4096 | 0 |  |
| `mcu rpi.mcu_constants.PWM_MAX` | 32768 | 0 |  |
| `mcu rpi.mcu_constants.STATS_SUMSQ_BASE` | 256 | 0 |  |
| `mcu rpi.mcu_constants.build_machine_uid` | "Feb 24 202417:48:08" | 0 |  |
| `mcu rpi.last_stats.mcu_awake` | 0.016 | 0.333 | 0.001 a 0.043 |
| `mcu rpi.last_stats.mcu_task_avg` | 0.000276 | 0.333 | 9e-06 a 0.000709 |
| `mcu rpi.last_stats.mcu_task_stddev` | 0.001153 | 0.333 | 1.1e-05 a 0.002613 |
| `mcu rpi.last_stats.bytes_write` | 97344 | 0.333 | 98131 a 100544 |
| `mcu rpi.last_stats.bytes_read` | 265839 | 0.333 | 267768 a 273700 |
| `mcu rpi.last_stats.bytes_retransmit` | 0 | 0.333 | 0 a 0 |
| `mcu rpi.last_stats.bytes_invalid` | 0 | 0.333 | 0 a 0 |
| `mcu rpi.last_stats.send_seq` | 14931 | 0.333 | 15044 a 15392 |
| `mcu rpi.last_stats.receive_seq` | 14931 | 0.333 | 15044 a 15392 |
| `mcu rpi.last_stats.retransmit_seq` | 0 | 0.333 | 0 a 0 |
| `mcu rpi.last_stats.srtt` | 0.001 | 0.333 | 0 a 0.005 |
| `mcu rpi.last_stats.rttvar` | 0.001 | 0.333 | 0 a 0.007 |
| `mcu rpi.last_stats.rto` | 0.025 | 0.333 | 0.025 a 0.033 |
| `mcu rpi.last_stats.ready_bytes` | 0 | 0.333 | 0 a 0 |
| `mcu rpi.last_stats.stalled_bytes` | 0 | 0.333 | 0 a 0 |
| `mcu rpi.last_stats.freq` | 49999993 | 0.333 | 49999978 a 50000045 |
| `mcu rpi.last_stats.adj` | 50000341 | 0.333 | 50000009 a 50000919 |
| `gcode_move.speed_factor` | 1 | 0 |  |
| `gcode_move.speed` | 9000 | 0.577 | 840 a 3e+04 |
| `gcode_move.extrude_factor` | 1 | 0 |  |
| `gcode_move.absolute_coordinates` | true | 0 |  |
| `gcode_move.absolute_extrude` | false | 0 |  |
| `gcode_move.homing_origin[0]` | 0 | 0 |  |
| `gcode_move.homing_origin[1]` | 0 | 0 |  |
| `gcode_move.homing_origin[2]` | 0 | 0 |  |
| `gcode_move.homing_origin[3]` | 0 | 0 |  |
| `gcode_move.position[0]` | 102.5 | 1.287 | 26.02 a 193.9 |
| `gcode_move.position[1]` | 82.81 | 1.287 | 81.61 a 178.4 |
| `gcode_move.position[2]` | 56.6 | 1.287 | 57.4 a 60.2 |
| `gcode_move.position[3]` | 4.213e+04 | 1.287 | 4.242e+04 a 4.341e+04 |
| `gcode_move.gcode_position[0]` | 102.5 | 1.287 | 26.02 a 193.9 |
| `gcode_move.gcode_position[1]` | 82.81 | 1.287 | 81.61 a 178.4 |
| `gcode_move.gcode_position[2]` | 56.6 | 1.287 | 57.4 a 60.2 |
| `gcode_move.gcode_position[3]` | 55.87 | 1.287 | -0.8 a 80.08 |
| `print_stats.filename` | "CAJA LISTA CARA ADALOVE LISTA PARA IMPRIMIR (1).stl_PETG... | 0 |  |
| `print_stats.total_duration` | 1.203e+04 | 3.97 | 1.213e+04 a 1.243e+04 |
| `print_stats.print_duration` | 1.198e+04 | 3.97 | 1.207e+04 a 1.237e+04 |
| `print_stats.filament_used` | 4.172e+04 | 1.287 | 4.202e+04 a 4.301e+04 |
| `print_stats.state` | "printing" | 0 |  |
| `print_stats.message` | "" | 0 |  |
| `print_stats.info.total_layer` | null | 0 |  |
| `print_stats.info.current_layer` | null | 0 |  |
| `print_stats.power_loss` | 0 | 0 |  |
| `print_stats.z_pos` | 56.63 | 0 |  |
| `virtual_sdcard.file_path` | "/mnt/UDISK/printer_data/gcodes/CAJA LISTA CARA ADALOVE L... | 0 |  |
| `virtual_sdcard.progress` | 0.4556 | 1.287 | 0.4603 a 0.4751 |
| `virtual_sdcard.is_active` | true | 0 |  |
| `virtual_sdcard.file_position` | 4703092 | 1.287 | 4751699 a 4904237 |
| `virtual_sdcard.file_size` | 10321936 | 0 |  |
| `virtual_sdcard.first_layer_stop` | false | 0 |  |
| `virtual_sdcard.layer` | 283 | 0.04 | 288 a 299 |
| `virtual_sdcard.layer_count` | 486 | 0 |  |
| `virtual_sdcard.run_dis` | 0 | 0 |  |
| `virtual_sdcard.klipper_capture` | false | 0 |  |
| `virtual_sdcard.cur_print_data.end_time` | 1.578e+09 | 0.003 | 1.578e+09 a 1.578e+09 |
| `virtual_sdcard.cur_print_data.filament_used` | 4.114e+04 | 0.003 | 4.284e+04 a 4.284e+04 |
| `virtual_sdcard.cur_print_data.filename` | "CAJA LISTA CARA ADALOVE LISTA PARA IMPRIMIR (1).stl_PETG... | 0.003 |  |
| `virtual_sdcard.cur_print_data.metadata` | {"size": 10321936, "modified": 1577837446.6100004, "uuid"... | 0.003 |  |
| `virtual_sdcard.cur_print_data.print_duration` | 1.18e+04 | 0.003 | 1.232e+04 a 1.232e+04 |
| `virtual_sdcard.cur_print_data.start_time` | 1.578e+09 | 0.003 | 1.578e+09 a 1.578e+09 |
| `virtual_sdcard.cur_print_data.status` | "in_progress" | 0.003 |  |
| `virtual_sdcard.cur_print_data.total_duration` | 1.186e+04 | 0.003 | 1.238e+04 a 1.238e+04 |
| `pause_resume.is_paused` | false | 0 |  |
| `pause_resume.resume_err` | false | 0 |  |
| `display_status.progress` | 0.53 | 0.007 | 0.54 a 0.55 |
| `display_status.message` | null | 0 |  |
| `custom_macro.leveling_calibration` | 0 | 0 |  |
| `custom_macro.default_extruder_temp` | 240 | 0 |  |
| `custom_macro.default_bed_temp` | 50 | 0 |  |
| `custom_macro.g28_ext_temp` | 140 | 0 |  |
| `custom_macro.qmode_flag` | 0 | 0 |  |
| `fan_feedback.fan0_speed` | 16000 | 0.007 | 12000 a 16000 |
| `fan_feedback.fan1_speed` | 6000 | 0.12 | 5333 a 6857 |
| `fan_feedback.fan2_speed` | 5333 | 0.09 | 5333 a 6857 |
| `fan_feedback.fan3_speed` | 0 | 0 |  |
| `fan_feedback.fan4_speed` | 0 | 0 |  |
| `filament_rack.vender` | "Creality" | 0 |  |
| `filament_rack.color_value` | "01B04AE" | 0 |  |
| `filament_rack.material_type` | "006001" | 0 |  |
| `box.filament` | 1 | 0 |  |
| `box.state` | "disconnect" | 0 |  |
| `box.auto_refill` | 1 | 0 |  |
| `box.enable` | 0 | 0 |  |
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
| `box.cut_state` | true | 0 |  |
| `motor_control.motor_ready` | true | 0 |  |
| `motor_control.is_homing` | false | 0 |  |
| `motor_control.cut.state` | true | 0 |  |
| `motor_control.cut.pos_x` | 279.6 | 0 |  |
| `idle_timeout.state` | "Printing" | 0 |  |
| `idle_timeout.printing_time` | 1.203e+04 | 3.97 | 1.213e+04 a 1.243e+04 |
| `heaters.available_heaters` | ["heater_bed", "extruder"] | 0 |  |
| `heaters.available_sensors` | ["temperature_sensor mcu_temp", "heater_bed", "extruder"] | 0 |  |
| `heaters.extruder_temperature_wait` | false | 0 |  |
| `heaters.bed_temperature_wait` | false | 0 |  |
| `temperature_sensor mcu_temp.temperature` | 55.72 | 3.24 | 54.89 a 56.73 |
| `temperature_sensor mcu_temp.measured_min_temp` | 33.88 | 0 |  |
| `temperature_sensor mcu_temp.measured_max_temp` | 57.03 | 0 |  |
| `tmc2208 stepper_z.mcu_phase_offset` | 31 | 0 |  |
| `tmc2208 stepper_z.phase_offset_position` | 601.6 | 0 |  |
| `tmc2208 stepper_z.run_current` | 0.4972 | 0 |  |
| `tmc2208 stepper_z.hold_current` | 0.4972 | 0 |  |
| `tmc2208 stepper_z.drv_status.cs_actual` | 14 | 0.107 | 14 a 14 |
| `tmc2208 stepper_z.drv_status.stealth` | 1 | 0.107 | 1 a 1 |
| `tmc2208 stepper_z.drv_status.stst` | 1 | 0.053 | 1 a 1 |
| `tmc2208 stepper_z1.mcu_phase_offset` | 2 | 0 |  |
| `tmc2208 stepper_z1.phase_offset_position` | 602.2 | 0 |  |
| `tmc2208 stepper_z1.run_current` | 0.4972 | 0 |  |
| `tmc2208 stepper_z1.hold_current` | 0.4972 | 0 |  |
| `tmc2208 stepper_z1.drv_status.cs_actual` | 14 | 0.087 | 14 a 14 |
| `tmc2208 stepper_z1.drv_status.stealth` | 1 | 0.087 | 1 a 1 |
| `tmc2208 stepper_z1.drv_status.stst` | 1 | 0.043 | 1 a 1 |
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
| `tmc2208 extruder.drv_status.cs_actual` | 29 | 0.1 | 29 a 29 |
| `heater_bed.temperature` | 79.69 | 2.66 | 79.93 a 80.33 |
| `heater_bed.target` | 80 | 0 |  |
| `heater_bed.power` | 0.4728 | 0.237 | 0.4223 a 0.4629 |
| `output_pin fanp0.value` | 1 | 0 |  |
| `output_pin fan0.value` | 0.3549 | 0.03 | 0.3588 a 0.449 |
| `output_pin board_fan.value` | 0 | 0 |  |
| `heater_fan hotend_fan.speed` | 1 | 0 |  |
| `heater_fan hotend_fan.rpm` | null | 0 |  |
| `bed_mesh.profile_name` | "default" | 0 |  |
| `bed_mesh.mesh_min[0]` | 10 | 0 |  |
| `bed_mesh.mesh_min[1]` | 10 | 0 |  |
| `bed_mesh.mesh_max[0]` | 250 | 0 |  |
| `bed_mesh.mesh_max[1]` | 250 | 0 |  |
| `bed_mesh.probed_matrix` | [[0.101, 0.085, 0.092, 0.108, 0.055, 0.052, 0.052, 0.085,... | 0 |  |
| `bed_mesh.mesh_matrix` | [[0.101, 0.096511, 0.089178, 0.085, 0.086207, 0.08937, 0.... | 0 |  |
| `bed_mesh.profiles.default` | {"points": [[0.101, 0.085, 0.092, 0.108, 0.055, 0.052, 0.... | 0 |  |
| `exclude_object.objects` | [{"name": "CAJA_LISTA_CARA_ADALOVE_LISTA_PARA_IMPRIMIR_1_... | 0 |  |
| `exclude_object.excluded_objects` | [] | 0 |  |
| `exclude_object.current_object` | "CAJA_LISTA_CARA_ADALOVE_LISTA_PARA_IMPRIMIR_1_.STL_ID_0_... | 0 |  |
| `filament_switch_sensor filament_sensor.filament_detected` | true | 0 |  |
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
| `motion_report.live_position[0]` | 28.6 | 3.97 | 26.02 a 193.9 |
| `motion_report.live_position[1]` | 166.3 | 3.97 | 81.61 a 178.4 |
| `motion_report.live_position[2]` | 56.63 | 3.97 | 57.43 a 60.21 |
| `motion_report.live_position[3]` | 4.211e+04 | 3.97 | 4.241e+04 a 4.34e+04 |
| `motion_report.live_velocity` | 150 | 2.557 | -2.842e-14 a 300 |
| `motion_report.live_extruder_velocity` | 4.468 | 2.913 | -40 a 40 |
| `motion_report.steppers` | ["extruder", "stepper_x", "stepper_y", "stepper_z", "step... | 0 |  |
| `motion_report.trapq` | ["extruder", "toolhead"] | 0 |  |
| `system_stats.sysload` | 0.63 | 0.2 | 0.25 a 0.94 |
| `system_stats.cputime` | 2864 | 0.333 | 2884 a 2944 |
| `system_stats.memavail` | 372932 | 0.327 | 371616 a 372696 |
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
| `toolhead.print_time` | 1.351e+04 | 1.283 | 1.361e+04 a 1.391e+04 |
| `toolhead.stalls` | 0 | 0 |  |
| `toolhead.estimated_print_time` | 1.351e+04 | 3.97 | 1.36e+04 a 1.39e+04 |
| `toolhead.extruder` | "extruder" | 0 |  |
| `toolhead.position[0]` | 102.5 | 1.287 | 26.02 a 193.9 |
| `toolhead.position[1]` | 82.81 | 1.287 | 81.61 a 178.4 |
| `toolhead.position[2]` | 56.63 | 1.287 | 57.43 a 60.23 |
| `toolhead.position[3]` | 4.213e+04 | 1.287 | 4.242e+04 a 4.341e+04 |
| `toolhead.max_velocity` | 300 | 0 |  |
| `toolhead.max_accel` | 5000 | 0.113 | 4800 a 6000 |
| `toolhead.max_accel_to_decel` | 2500 | 0.113 | 2400 a 3000 |
| `toolhead.square_corner_velocity` | 8 | 0.083 | 8 a 12 |
| `toolhead.G29_flag` | false | 0 |  |
| `extruder.temperature` | 249.4 | 3.127 | 249.2 a 250.9 |
| `extruder.target` | 250 | 0 |  |
| `extruder.power` | 0.413 | 0.98 | 0.1611 a 0.6629 |
| `extruder.can_extrude` | true | 0 |  |
| `extruder.nozzle_diameter` | 0.4 | 0 |  |
| `extruder.extrude_below_min_temp_err_is_report` | false | 0 |  |
| `extruder.pressure_advance` | 0.072 | 0 |  |
| `extruder.smooth_time` | 0.04 | 0 |  |
