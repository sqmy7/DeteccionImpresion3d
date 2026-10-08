# Configuración de Klipper (análisis automático)

Fuente: objeto `configfile` (`configfile.json`). Lo regenera `moonraker_discovery.py` en cada corrida.

## Límites de los ejes

| Eje | position_min | position_max | position_endstop |
|---|---|---|---|
| stepper_x | -19.0 | 285.0 | -19.0 |
| stepper_y | -7.0 | 273.0 | -7.0 |
| stepper_z | -5.0 | 310.0 | - |

Cinemática `cartesian`, max_velocity 300.0 mm/s, max_accel 12000.0 mm/s².

## Malla de la cama

mesh_min [10.0, 10.0], mesh_max [250.0, 250.0], probe_count [9, 9].

`exclude_object` configurado: no.

## Macros relevantes para el incidente

### `gcode_macro CANCEL_PRINT`

```
[gcode_macro CANCEL_PRINT]
description: Cancel the actual running print
rename_existing: CANCEL_PRINT_BASE
variable_inside_cancel: 0
gcode:
  ENABLE_PRESSURE_ADVANCE VALUE=1
  {action_respond_info("CANCEL_PRINT trigger ENABLE_PRESSURE_ADVANCE=1")}
  RESPONSE_INFO MSG="Canceling print"
  SET_GCODE_VARIABLE MACRO=CANCEL_PRINT VARIABLE=inside_cancel VALUE=1
  {% set inside_cancel = printer['gcode_macro CANCEL_PRINT'].inside_cancel|int %}
  RESPONSE_INFO MSG="inside_cancel:{inside_cancel}"
  {% set act_z = printer.toolhead.position.z|float %}
  {% if act_z + 50 > 305 %}
  {% set pos_z = 305 %}
  {% else %}
  {% set pos_z = printer.toolhead.position.z|float + 50 %}
  {% endif %}
  {% if "xyz" in printer.toolhead.homed_axes %}
  G90
  G1 Z{pos_z} F1200
  {% else %}
  {action_respond_info("Printer not homed")}
  G28 X Y
  {% endif %}
  
  CANCEL_PRINT_BASE
  PAUSE_CUT
  FORCE_MOVE_E E=-2
  TURN_OFF_HEATERS
  G1 F3000 X10 Y260
  M400
  M104 S0
  M140 S0
  M107
  M84
  FINISH_INIT
  
  BOX_END_PRINT
  SET_GCODE_VARIABLE MACRO=CANCEL_PRINT VARIABLE=inside_cancel VALUE=0
  RESPONSE_INFO MSG="inside_cancel:{inside_cancel}"
  RESPONSE_INFO MSG="Print canceled"
```

### `gcode_macro END_PRINT`

```
[gcode_macro END_PRINT]
gcode:
  ENABLE_PRESSURE_ADVANCE VALUE=1
  {action_respond_info("END_PRINT trigger ENABLE_PRESSURE_ADVANCE=1")}
  {% set act_z = printer.toolhead.position.z|float %}
  {% if act_z + 50 > 305 %}
  {% set pos_z = 305 %}
  {% else %}
  {% set pos_z = printer.toolhead.position.z|float + 50 %}
  {% endif %}
  G1 F3000 Z{pos_z}
  BOX_END
  BOX_END_PRINT
  G1 F3000 X0 Y260
  M104 S0
  M140 S0
  M107
  M84
```

### `gcode_macro FIRST_FLOOR_PAUSE`

```
[gcode_macro FIRST_FLOOR_PAUSE]
description: Pause the first floor print
variable_extrude: 2.0
gcode:
  {% set E = printer["gcode_macro FIRST_FLOOR_PAUSE"].extrude|float %}
  
  
  {% set y_park = printer.toolhead.axis_maximum.y/2 %}
  {% set x_park = printer.toolhead.axis_maximum.x|float - 10.0 %}
  
  {% set max_z = printer["gcode_macro PRINTER_PARAM"].max_z_position|float %}
  {% set act_z = printer.toolhead.position.z|float %}
  {% set z_safe = 0.0 %}
  {% if act_z < (max_z - 2.0) %}
  {% set z_safe = 2.0 %}
  {% elif act_z < max_z %}
  {% set z_safe = max_z - act_z %}
  {% endif %}
  
  SET_GCODE_VARIABLE MACRO=PRINTER_PARAM VARIABLE=z_safe_pause VALUE={z_safe|float}
  PAUSE_BASE
  G91
  {% if "xyz" in printer.toolhead.homed_axes %}
  {% if printer.extruder.can_extrude|lower == 'true' %}
  G1 E-1.0 F180
  G1 E-{E} F4000
  {% else %}
  {action_respond_info("Extruder not hot enough")}
  {% endif %}
  G1 Z{z_safe} F600
  G90
  G1 X{x_park} Y{y_park} F30000
  {% else %}
  {action_respond_info("Printer not homed")}
  {% endif %}
```

### `gcode_macro FIRST_FLOOR_PAUSE_POSITION`

```
[gcode_macro FIRST_FLOOR_PAUSE_POSITION]
gcode:
  {% set extruder_temp = printer.custom_macro.g28_ext_temp %}
  M104 S{extruder_temp}
  {% set y_park = printer.toolhead.axis_maximum.y/2 %}
  {% set x_park = printer['gcode_macro PRINTER_PARAM'].max_x_position|float + 1 %}
  G90
  G1 Z2 F600
  G1 X{x_park} Y{y_park} F6000
  G1 Z0.2 F600
```

### `gcode_macro FIRST_FLOOR_RESUME`

```
[gcode_macro FIRST_FLOOR_RESUME]
description: Resume the first floor print
gcode:
  {% set E = printer["gcode_macro FIRST_FLOOR_PAUSE"].extrude|float + 1.0 %}
  
  {% if 'VELOCITY' in params|upper %}
  {% set get_params = ('VELOCITY=' + params.VELOCITY) %}
  {%else %}
  {% set get_params = "" %}
  {% endif %}
  
  {% if printer.extruder.can_extrude|lower == 'true' %}
  G91
  G1 E{E} F2100
  {% else %}
  {action_respond_info("Extruder not hot enough")}
  {% endif %}
  RESUME_BASE {get_params}
```

### `gcode_macro M600`

```
[gcode_macro M600]
gcode:
  PAUSE
  {% set act_e = printer.toolhead.position.e|float %}
  G91
  G1 E20 F180
  G1 E-30 F180
  G1 E-50 F600
  G90
  G92 E{act_e}
```

### `gcode_macro PAUSE`

```
[gcode_macro PAUSE]
description: Pause the actual running print
rename_existing: PAUSE_BASE
variable_extrude: 2.0
gcode:
  {% if printer.pause_resume.is_paused|lower == 'false' %}
  PAUSE_BASE
  PAUSE_EXTERNAL
  {% endif %}
```

### `gcode_macro PAUSE_EXTERNAL`

```
[gcode_macro PAUSE_EXTERNAL]
gcode:
  {% set inside_cancel = printer['gcode_macro CANCEL_PRINT'].inside_cancel|int %}
  RESPONSE_INFO MSG="Pausing print, inside_cancel:{inside_cancel}"
  {% if printer['print_stats'].state|lower == 'cancelled' %}
  RESPONSE_INFO MSG="PAUSE: printer state is not printing."
  {% else %}
  {% if printer['gcode_macro CANCEL_PRINT'].inside_cancel|int == 0 %}
  { action_respond_info("Printer is pausing.\n") }
  
  {% set E = printer["gcode_macro PAUSE"].extrude|float %}
  
  
  
  
  
  
  {% set max_z = printer.toolhead.axis_maximum.z|float %}
  {% set act_z = printer.toolhead.position.z|float %}
  {% if act_z < 48.0 %}
  {% set z_safe = 50.0 - act_z %}
  {% elif act_z < (max_z - 2.0) %}
  {% set z_safe = 2.0 %}
  {% else %}
  {% set z_safe = max_z - act_z %}
  {% endif %}
  SET_GCODE_VARIABLE MACRO=PRINTER_PARAM VARIABLE=z_safe_pause VALUE={z_safe|float}
  
  SET_GCODE_VARIABLE MACRO=PRINTER_PARAM VARIABLE=hotend_temp VALUE={printer.extruder.target}
  {% if printer.extruder.can_extrude|lower == 'true' %}
  G91
  G1 E-1.0 F180
  G1 E-{E} F360
  G90
  {% else %}
  {action_respond_info("Extruder not hot enough")}
  {% endif %}
  {% if "xyz" in printer.toolhead.homed_axes %}
  G91
  G1 Z{z_safe} F600
  G90
  M400
  IF_CUT_AND_COOLING
  {% else %}
  {action_respond_info("Printer not homed")}
  {% endif %}
  {% else %}
  {action_respond_info("Printer is canceling, no need to pause")}
  {% endif %}
  {% endif %}
  BOX_TIGHTEN_UP_ENABLE ENABLE=ENABLE
```

### `gcode_macro RESUME`

```
[gcode_macro RESUME]
description: Resume the actual running print
rename_existing: RESUME_BASE
gcode:
  RESUME_BOX_ERROR_CLEAR
  RESUME_EXTERNAL_PROCESS
  RESUME_BASE {get_params}
```

### `gcode_macro RESUME_EXTERNAL`

```
[gcode_macro RESUME_EXTERNAL]
gcode:
  {% if printer.pause_resume.resume_err is none or printer.pause_resume.resume_err|lower == 'false' %}
  SET_GCODE_VARIABLE MACRO=IF_CUT_AND_COOLING VARIABLE=resumed VALUE=1
  {% if printer['gcode_macro PRINTER_PARAM'].hotend_temp|int != 0 %}
  {% if printer['gcode_macro PRINTER_PARAM'].hotend_temp|int > printer.extruder.temperature %}
  M109 S{printer['gcode_macro PRINTER_PARAM'].hotend_temp|int}
  {% else %}
  M104 S{printer['gcode_macro PRINTER_PARAM'].hotend_temp|int}
  {% endif %}
  SET_GCODE_VARIABLE MACRO=PRINTER_PARAM VARIABLE=hotend_temp VALUE=0
  {% endif %}
  
  {% set E = printer["gcode_macro PAUSE"].extrude|float + 60.0 %}
  
  {% if 'VELOCITY' in params|upper %}
  {% set get_params = ('VELOCITY=' + params.VELOCITY)  %}
  {%else %}
  {% set get_params = "" %}
  {% endif %}
  {% set z_resume_move = printer['gcode_macro PRINTER_PARAM'].z_safe_pause|int %}
  {% if z_resume_move > 2 %}
  {% set z_resume_move = z_resume_move - 2 %}
  G91
  G1 Z-{z_resume_move} F600
  M400
  {% endif %}
  
  
  {% if printer.extruder.can_extrude|lower == 'false' %}
  {action_respond_info("Extruder not hot enough, SET M109 S%s" %
  printer['gcode_macro PRINTER_PARAM'].hotend_temp|int)}
  M109 S{printer['gcode_macro PRINTER_PARAM'].hotend_temp|int}
  {% else %}
  M104 S{printer['gcode_macro PRINTER_PARAM'].hotend_temp|int}
  {% endif %}
  {% if printer['gcode_macro PRINTER_PARAM'].hotend_temp|int > printer.extruder.temperature %}
  IF_NEED_HOME
  BOX_GO_TO_EXTRUDE_POS
  
  
  RESUME_FLUSH LENGTH={E}
  M400
  BOX_NOZZLE_CLEAN
  M109 S{printer['gcode_macro PRINTER_PARAM'].hotend_temp|int}
  {% else %}
  RESPONSE_INFO MSG="Last hotend_temp below minimum extruder temperature"
  {% endif %}
  
  
  {% if printer['gcode_macro PRINTER_PARAM'].fan0_speed > 0 %}
  {% set s_value = (printer['gcode_macro PRINTER_PARAM'].fan0_speed * 255 - printer['gcode_macro PRINTER_PARAM'].fan0_min) * 255 / (255 - printer['gcode_macro PRINTER_PARAM'].fan0_min)|float %}
  M106 S{s_value}
  
  SET_GCODE_VARIABLE MACRO=PRINTER_PARAM VARIABLE=fan0_speed VALUE=0
  {% endif %}
  BOX_TIGHTEN_UP_ENABLE ENABLE=DISABLE
  {% endif %}
```

### `gcode_macro RESUME_EXTERNAL_PROCESS`

```
[gcode_macro RESUME_EXTERNAL_PROCESS]
gcode:
  BOX_ERROR_RESUME_PROCESS
  RESUME_EXTERNAL
```

### `gcode_macro START_PRINT`

```
[gcode_macro START_PRINT]
variable_prepare: 0
gcode:
  Rmode_exit
  BOX_ERROR_CLEAR
  BOX_START_PRINT
  {% set acc = printer["gcode_macro PRINTER_PARAM"].default_acc %}
  G90
  SET_GCODE_OFFSET Z=0
  SET_VELOCITY_LIMIT SQUARE_CORNER_VELOCITY=10
  M204 S{acc}
  SET_VELOCITY_LIMIT ACCEL_TO_DECEL=8000
  {% set g28_extruder_temp = printer.custom_macro.g28_ext_temp %}
  {% set bed_temp = printer.custom_macro.default_bed_temp %}
  {% set extruder_temp = printer.custom_macro.default_extruder_temp %}
  {% set BED_TEMP = params.BED_TEMP|default(45)|float %}
  {% set EXTRUDER_TEMP = params.EXTRUDER_TEMP|default(200)|float %}
  {% set EXTRUDER_WAITTEMP = (EXTRUDER_TEMP/1.5|float)|int %}
  
  {% if printer['gcode_macro START_PRINT'].prepare|int == 0 %}
  {action_respond_info("print prepared 111")}
  M106 S0
  M140 S{params.BED_TEMP}
  M104 S{EXTRUDER_WAITTEMP}
  G28 X Y
  NOZ_CLEAR
  ZDOWN_SWITCH ENABLE=1
  G28 Z
  BOX_GO_TO_EXTRUDE_POS
  M190 S{params.BED_TEMP}
  
  
  ZDOWN_SWITCH ENABLE=0
  
  
  SET_PIN PIN=fan0 VALUE=127
  M109 S45
  M106 S0
  NEXT_HOMEZ_NACCU
  G28 Z
  BED_MESH_CALIBRATE
  CXSAVE_CONFIG
  {% else %}
  {action_respond_info("print prepared 222")}
  PRINT_PREPARE_CLEAR
  {% endif %}
  G0 X0 Y0 Z3 F12000
  M104 S{params.EXTRUDER_TEMP}
  
  BOX_GO_TO_EXTRUDE_POS
  M109 S{params.EXTRUDER_TEMP}
  M140 S{params.BED_TEMP}
  M220 S100
  M221 S100
  G21
  G92 E0
```

Todas las macros (71) están en `macros.cfg`.

## Secciones no reconocidas como Klipper estándar

- `auto_addr`
- `bl24c16f`
- `box`
- `custom_macro`
- `delayed_gcode COOLING_AFTER_PRINTER_PAUSED`
- `delayed_gcode CUT_AND_COOLING_AFTER_PRINTER_PAUSED`
- `delayed_gcode DELAY_DISABLE_EXTRUDER`
- `delayed_gcode STARTUP_READ_FILAMENT_RACK_RFID`
- `delayed_gcode wait_temp`
- `fan_feedback`
- `filament_rack`
- `io_remap`
- `motor_control`
- `nozzle_clear`
- `prtouch_v3`
- `serial_485 serial485`
- `steer`
- `timer_read`
- `tmc_line_check`
- `z_align`
