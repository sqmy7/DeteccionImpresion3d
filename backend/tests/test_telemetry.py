from datetime import datetime, timedelta, timezone

from app.services.telemetry import build_subscription, clean_row, downsample, layer_snapshot, sample_from_status

# Shape of a Creality Hi status mid-print (fields as Klipper and the Creality firmware report them).
_STATUS = {
    "print_stats": {"state": "printing", "filament_used": 1234.5678, "info": {"total_layer": None, "current_layer": None}},
    "virtual_sdcard": {"layer": 42, "layer_count": 125, "progress": 0.3361},
    "motion_report": {"live_position": [120.5, 98.25, 8.4, 1234.0], "live_velocity": 180.0, "live_extruder_velocity": 6.2},
    "toolhead": {"position": [121.0, 99.0, 8.4, 1234.1]},
    "gcode_move": {"speed_factor": 0.9, "extrude_factor": 1.05, "homing_origin": [0.0, 0.0, -0.05, 0.0]},
    "extruder": {"temperature": 239.87, "target": 240.0, "power": 0.41},
    "heater_bed": {"temperature": 70.02, "target": 70.0, "power": 0.33},
    "fan": {"speed": 0.5, "rpm": None},
    "exclude_object": {"current_object": "BOX_2"},
    "temperature_sensor chamber": {"temperature": 31.2},
    "heater_fan hotend_fan": {"speed": 1.0, "rpm": None},
    "filament_switch_sensor filament_sensor": {"filament_detected": True, "enabled": True},
}


def test_subscription_covers_the_core_objects_and_every_optional_sensor():
    objects = ["print_stats", "virtual_sdcard", "extruder", "temperature_sensor chamber", "heater_fan hotend_fan", "box"]
    subscription = build_subscription(objects)

    assert subscription["print_stats"] is None
    assert subscription["extruder"] == ["temperature", "target", "power"]
    assert subscription["temperature_sensor chamber"] == ["temperature"]
    assert subscription["heater_fan hotend_fan"] == ["speed", "rpm"]
    assert "heater_bed" not in subscription  # not listed by this printer
    assert "box" not in subscription  # unknown objects are left out


def test_subscription_without_object_list_falls_back_to_the_core_set():
    subscription = build_subscription(None)
    assert {"print_stats", "virtual_sdcard", "toolhead", "extruder", "heater_bed"} <= subscription.keys()


def test_sample_reads_creality_layer_and_live_position():
    sample = sample_from_status(_STATUS)

    assert sample["layer_number"] == 42
    assert (sample["x"], sample["y"], sample["z"]) == (120.5, 98.25, 8.4)  # live, not the queued position
    assert sample["extruder_temp"] == 239.87
    assert sample["speed_factor"] == 0.9
    assert sample["z_offset"] == -0.05
    assert sample["filament_used"] == 1234.5678
    assert sample["extra"] == {
        "temperature_sensor chamber.temperature": 31.2,
        "heater_fan hotend_fan.speed": 1.0,
        "filament_switch_sensor filament_sensor.filament_detected": True,
        "filament_switch_sensor filament_sensor.enabled": True,
    }


def test_sample_tolerates_missing_objects_and_odd_values():
    sample = sample_from_status({"print_stats": {"info": {"current_layer": 7}}, "extruder": {"temperature": "n/a"}})

    assert sample["layer_number"] == 7  # upstream Klipper's field when Creality's is absent
    assert sample["extruder_temp"] is None
    assert sample["x"] is None
    assert sample["extra"] is None


def test_layer_snapshot_keeps_the_object_being_printed():
    snapshot = layer_snapshot(_STATUS)

    assert snapshot["current_object"] == "BOX_2"
    assert snapshot["bed_temp"] == 70.02
    assert "layer_number" not in snapshot


def test_downsample_averages_buckets_and_keeps_cumulative_values():
    start = datetime(2026, 10, 7, 20, 0, tzinfo=timezone.utc)
    points = [
        {
            "ts": start + timedelta(seconds=second),
            "layer_number": second // 10,
            "extruder_temp": 200.0 + second,
            "filament_used": float(second),
            "extra": {"temperature_sensor chamber.temperature": 30.0},
        }
        for second in range(100)
    ]

    thinned, width = downsample(points, max_points=10)

    assert width == 11.0  # 99 s spread over 10 buckets
    assert len(thinned) == 10
    first = thinned[0]
    assert first["extruder_temp"] == 205.0  # mean of 200..210
    assert first["filament_used"] == 10.0  # last value, not the mean
    assert first["extra"] == {"temperature_sensor chamber.temperature": 30.0}
    assert thinned[-1]["filament_used"] == 99.0


def test_clean_row_removes_real_column_noise():
    row = {"extruder_temp": 25.110000610351562, "layer_number": 3, "extra": None, "progress": 0.9932000041007996}
    assert clean_row(row) == {"extruder_temp": 25.11, "layer_number": 3, "extra": None, "progress": 0.9932}


def test_downsample_returns_small_series_untouched():
    points = [{"ts": datetime.now(timezone.utc), "extruder_temp": 1.0}]
    assert downsample(points, max_points=10) == (points, None)
