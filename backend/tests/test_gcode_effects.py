import pytest

from app.integrations.moonraker.gcode_effects import (
    Effect,
    FileIndex,
    GcodeScanner,
    direct_effects,
    explains,
    line_effects,
    macros_from_config,
)

_MACROS = {
    "START_PRINT": "G28\nM190 S{params.BED_TEMP|float}\nM109 S{params.EXTRUDER_TEMP|default(220)|float}\nPURGE_LINE",
    "END_PRINT": "TURN_OFF_HEATERS\nM107\n{% if printer.toolhead.position.z < 200 %}\nG91\n{% endif %}",
    "PURGE_LINE": "M106 S{printer.fan.speed * 255}",
    "LOOP": "LOOP",
}


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("M104 S245", [Effect("extruder.target", 245.0)]),
        ("M109 S240 ; wait", [Effect("extruder.target", 240.0)]),
        ("M104 T1 S200", [Effect("extruder1.target", 200.0)]),
        ("m140 s70", [Effect("heater_bed.target", 70.0)]),
        ("SET_HEATER_TEMPERATURE HEATER=heater_bed TARGET=65", [Effect("heater_bed.target", 65.0)]),
        ("SET_HEATER_TEMPERATURE HEATER=chamber TARGET=40", [Effect("heater_generic chamber.target", 40.0)]),
        ("SET_HEATER_TEMPERATURE HEATER=extruder", [Effect("extruder.target", 0.0)]),
        ("M220 S80", [Effect("gcode_move.speed_factor", 0.8)]),
        ("M221 S95", [Effect("gcode_move.extrude_factor", 0.95)]),
        ("M106 S128", [Effect("fan.speed", 128 / 255)]),
        ("M106", [Effect("fan.speed", 1.0)]),
        ("M107", [Effect("fan.speed", 0.0)]),
        ("SET_FAN_SPEED FAN=aux SPEED=0.4", [Effect("fan_generic aux.speed", 0.4)]),
        ("SET_GCODE_OFFSET Z_ADJUST=-0.025 MOVE=1", [Effect("gcode_move.homing_origin[2]", None)]),
        ("SET_GCODE_OFFSET Z=0.1", [Effect("gcode_move.homing_origin[2]", 0.1)]),
        ("EXCLUDE_OBJECT NAME=BOX_2", [Effect("exclude_object.excluded_objects", "BOX_2")]),
        ("EXCLUDE_OBJECT NAME='Part 1'", [Effect("exclude_object.excluded_objects", "Part 1")]),
        ("PAUSE", [Effect("print_stats.state", "paused")]),
        ("M600", [Effect("print_stats.state", "paused")]),
        ("RESUME", [Effect("print_stats.state", "printing")]),
        ("CANCEL_PRINT", [Effect("print_stats.state", "cancelled")]),
        ("G1 X10 Y10 E1.5", []),
        ("; M104 S200 in a comment", []),
        ("EXCLUDE_OBJECT", []),
    ],
)
def test_direct_effects(line, expected):
    assert direct_effects(line) == expected


def test_macro_parameters_are_resolved_from_the_call():
    effects = line_effects("START_PRINT BED_TEMP=70 EXTRUDER_TEMP=240", _MACROS)
    assert (Effect("heater_bed.target", 70.0), "START_PRINT") in effects
    assert (Effect("extruder.target", 240.0), "START_PRINT") in effects


def test_missing_macro_parameter_uses_its_default():
    effects = line_effects("START_PRINT BED_TEMP=60", _MACROS)
    assert (Effect("extruder.target", 220.0), "START_PRINT") in effects


def test_unresolvable_template_means_any_value_and_nested_macros_are_followed():
    effects = line_effects("START_PRINT BED_TEMP=60", _MACROS)
    assert (Effect("fan.speed", None), "START_PRINT > PURGE_LINE") in effects


def test_every_branch_of_a_macro_counts():
    effects = [effect for effect, _ in line_effects("END_PRINT", _MACROS)]
    assert Effect("extruder.target", 0.0) in effects
    assert Effect("fan.speed", 0.0) in effects


def test_recursive_macros_stop():
    assert line_effects("LOOP", _MACROS) == []


@pytest.mark.parametrize(
    ("effect", "field", "value", "expected"),
    [
        (Effect("extruder.target", 245.0), "extruder.target", 245.0, True),
        (Effect("extruder.target", 245.0), "extruder.target", 240.0, False),
        (Effect("fan.speed", 128 / 255), "fan.speed", 0.502, True),
        (Effect("gcode_move.homing_origin[2]", None), "gcode_move.homing_origin[2]", -0.025, True),
        (Effect("heater_bed.target", 70.0), "extruder.target", 70.0, False),
        (Effect("print_stats.state", "paused"), "print_stats.state", "paused", True),
    ],
)
def test_explains(effect, field, value, expected):
    assert explains(effect, field, value) is expected


def test_macros_are_read_from_the_printer_configuration():
    config = {"gcode_macro start_print": {"gcode": "\nM190 S60"}, "stepper_x": {"position_max": "260"}}
    assert macros_from_config(config) == {"START_PRINT": "\nM190 S60"}


def test_scanner_records_byte_offsets_across_chunks():
    text = b";header\nSTART_PRINT BED_TEMP=70 EXTRUDER_TEMP=240\nG1 X1 Y1\nM104 S235\nG1 X2\nM106 S128\nEND_PRINT"
    scanner = GcodeScanner(_MACROS)
    for start in range(0, len(text), 7):  # tiny chunks split lines in the middle
        scanner.feed(text[start : start + 7])
    scanner.finish()

    index = FileIndex("box.gcode", scanner.commands, scanner.bytes_scanned, complete=True)
    m104 = text.index(b"M104")
    assert index.find("extruder.target", 235.0, m104 - 10, m104 + 10).offset == m104
    assert index.find("extruder.target", 235.0, 0, m104 - 1) is None  # outside the window
    start_print = index.find("heater_bed.target", 70.0, 0, 20)
    assert start_print.via == "START_PRINT" and start_print.offset == text.index(b"START_PRINT")
    assert index.find("fan.speed", 0.0, len(text) - 20, len(text)).line == "END_PRINT"
    assert scanner.bytes_scanned == len(text)
