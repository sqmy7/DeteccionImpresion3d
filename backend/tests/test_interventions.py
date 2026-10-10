from datetime import datetime, timezone
from email.utils import format_datetime

from app.integrations.moonraker.gcode_effects import Effect, FileCommand, FileIndex
from app.integrations.moonraker.interventions import (
    ClockOffset,
    ConsoleCommand,
    DetectedChange,
    FieldChange,
    classify,
    detect_changes,
    print_phase,
)

_PREVIOUS = {
    "extruder": {"temperature": 239.8, "target": 240.0},
    "heater_bed": {"target": 70.0},
    "gcode_move": {"speed_factor": 1.0, "extrude_factor": 1.0, "homing_origin": [0.0, 0.0, 0.0, 0.0]},
    "fan": {"speed": 0.0},
    "exclude_object": {"excluded_objects": []},
    "webhooks": {"state": "ready"},
    "filament_switch_sensor runout": {"filament_detected": True},
}


def test_detect_changes_reports_only_watched_fields_that_changed():
    patch = {
        "extruder": {"temperature": 241.0, "target": 250.0},  # temperature isn't watched
        "gcode_move": {"speed_factor": 0.8, "homing_origin": [0.0, 0.0, -0.05, 0.0]},
        "exclude_object": {"excluded_objects": ["BOX_2"]},
        "webhooks": {"state": "shutdown"},
        "filament_switch_sensor runout": {"filament_detected": False},
        "heater_bed": {"target": 70.0},  # same value
    }

    changes = detect_changes(_PREVIOUS, patch)

    assert changes == [
        FieldChange("target_changed", "extruder.target", 240.0, 250.0, True),
        FieldChange("speed_factor_changed", "gcode_move.speed_factor", 1.0, 0.8, True),
        FieldChange("z_offset_changed", "gcode_move.homing_origin[2]", 0.0, -0.05, True),
        FieldChange("object_excluded", "exclude_object.excluded_objects", None, "BOX_2", True),
        FieldChange("klippy_state_changed", "webhooks.state", "ready", "shutdown", False),
        FieldChange("filament_sensor_changed", "filament_switch_sensor runout.filament_detected", True, False, False),
    ]


def test_a_field_seen_for_the_first_time_is_not_a_change():
    assert detect_changes({}, {"extruder": {"target": 240.0}}) == []


def test_print_phase():
    assert print_phase("standby", None, None, has_job=False) == "idle"
    assert print_phase("printing", 0, 0.01, has_job=True) == "start"
    assert print_phase("printing", 12, 0.4, has_job=True) == "printing"
    assert print_phase("printing", 125, 0.998, has_job=True) == "end"
    assert print_phase("paused", 12, 0.4, has_job=True) == "paused"


def _change(field="extruder.target", after=250.0, event_type="target_changed", observed=100.0, before_pos=5000, after_pos=6000):
    return DetectedChange(
        event_type=event_type,
        field=field,
        before=240.0,
        after=after,
        observed_at=datetime(2026, 10, 7, tzinfo=timezone.utc),
        observed_monotonic=observed,
        klipper_eventtime=None,
        filename="box.gcode",
        file_position_before=before_pos,
        file_position_after=after_pos,
        phase="printing",
        job_id=1,
    )


def _index(*commands: tuple[int, str, Effect]) -> FileIndex:
    return FileIndex("box.gcode", [FileCommand(offset, line, effect, "") for offset, line, effect in commands], 10_000, True)


def test_console_command_wins_and_explains_one_change_per_field():
    command = ConsoleCommand("M104 S250", 1_791_000_000.0, 101.5, [Effect("extruder.target", 250.0)])

    first = classify(_change(), [command], None, False, now=102.0)
    second = classify(_change(observed=103.0), [command], None, False, now=200.0)

    assert first.origin == "console" and first.record and first.detail["command"] == "M104 S250"
    assert second.origin == "external"  # the same command can't explain a second change


def test_file_line_inside_the_read_window_explains_the_change():
    index = _index((5500, "M104 S250", Effect("extruder.target", 250.0)))
    decision = classify(_change(), [], index, False, now=100.5)
    assert decision.origin == "gcode_file" and decision.detail == {"line": "M104 S250", "offset": 5500}


def test_file_line_outside_the_window_does_not():
    index = _index((9000, "M104 S250", Effect("extruder.target", 250.0)))
    assert classify(_change(), [], index, False, now=100.5) is None  # still waiting for the console
    decision = classify(_change(), [], index, False, now=110.0)
    assert decision.origin == "external" and decision.detail == {"file_checked": True}


def test_waits_for_the_console_then_for_the_file_index():
    assert classify(_change(), [], None, file_scan_running=True, now=103.0) is None
    assert classify(_change(), [], None, file_scan_running=True, now=150.0) is None
    decision = classify(_change(), [], None, file_scan_running=True, now=400.0)
    assert decision.origin == "external" and decision.detail == {"file_checked": False}


def test_clock_offset_narrows_down_from_whole_second_date_headers():
    clock = ClockOffset()
    for local in (1000.0, 1000.4, 1000.75, 1001.2):
        printer_now = local + 2.3  # the printer's clock runs 2.3 s ahead
        header = format_datetime(datetime.fromtimestamp(int(printer_now), timezone.utc), usegmt=True)
        clock.update(header, local, local)

    assert clock.low <= 2.3 <= clock.high
    assert clock.high - clock.low < 0.5
    assert abs(clock.to_local(1_000_002.3).timestamp() - 1_000_000.0) < 0.3


def test_clock_offset_starts_over_when_the_printer_clock_jumps():
    clock = ClockOffset()
    clock.update(format_datetime(datetime.fromtimestamp(1002, timezone.utc), usegmt=True), 1000.0, 1000.0)
    clock.update(format_datetime(datetime.fromtimestamp(5000, timezone.utc), usegmt=True), 1001.0, 1001.0)
    assert 3999 <= clock.seconds <= 4000


def test_programmed_fan_changes_are_not_logged_and_unexplained_ones_only_with_the_file_checked():
    fan = dict(field="fan.speed", after=0.5, event_type="fan_changed")
    programmed = classify(_change(**fan), [], _index((5600, "M106 S128", Effect("fan.speed", 128 / 255))), False, now=101)
    unchecked = classify(_change(**fan), [], None, False, now=200)
    checked = classify(_change(**fan), [], _index(), False, now=200)

    assert programmed.origin == "gcode_file" and programmed.record is False
    assert unchecked.record is False
    assert checked.record is True and checked.origin == "external"
