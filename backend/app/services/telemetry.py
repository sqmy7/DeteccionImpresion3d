"""Telemetry read from Moonraker: which Klipper objects to subscribe to, how the merged status
becomes a stored sample or a per-layer snapshot, and how a job's series is thinned for charts.
Pure functions (no I/O), so they are tested without a printer."""

from collections.abc import Iterable
from datetime import datetime

# Objects every Klipper printer has, with the fields PrintWatch uses (None = all fields).
# print_stats and virtual_sdcard go whole: the job/layer logic and Creality's own fields
# (virtual_sdcard.layer, layer_count, cur_print_data) live there.
_CORE_SUBSCRIPTION: dict[str, list[str] | None] = {
    "print_stats": None,
    "virtual_sdcard": None,
    "webhooks": ["state", "state_message"],
    "toolhead": ["position", "homed_axes", "axis_minimum", "axis_maximum"],
    "motion_report": ["live_position", "live_velocity", "live_extruder_velocity"],
    "gcode_move": ["speed_factor", "extrude_factor", "homing_origin", "speed"],
    "extruder": ["temperature", "target", "power"],
    "heater_bed": ["temperature", "target", "power"],
    "fan": ["speed", "rpm"],
    "idle_timeout": ["state"],
    "pause_resume": ["is_paused"],
    "exclude_object": ["objects", "excluded_objects", "current_object"],
    "bed_mesh": ["profile_name", "mesh_min", "mesh_max", "probed_matrix"],
}

# Optional sensors and fans, matched by the prefix of their Klipper object name.
_PREFIXED_SUBSCRIPTION: dict[str, list[str]] = {
    "temperature_sensor ": ["temperature"],
    "temperature_fan ": ["temperature", "target", "speed"],
    "heater_generic ": ["temperature", "target", "power"],
    "heater_fan ": ["speed", "rpm"],
    "controller_fan ": ["speed", "rpm"],
    "fan_generic ": ["speed", "rpm"],
    "filament_switch_sensor ": ["filament_detected", "enabled"],
    "filament_motion_sensor ": ["filament_detected", "enabled"],
}

# Columns of telemetry_samples filled from the status (besides job, time and extra).
SAMPLE_FIELDS = (
    "layer_number",
    "x",
    "y",
    "z",
    "velocity",
    "extruder_velocity",
    "extruder_temp",
    "extruder_target",
    "extruder_power",
    "bed_temp",
    "bed_target",
    "bed_power",
    "fan_speed",
    "speed_factor",
    "extrude_factor",
    "z_offset",
    "progress",
    "filament_used",
)

# Fields that only grow during a print: a bucket keeps its last value instead of the average.
_CUMULATIVE_FIELDS = {"layer_number", "progress", "filament_used"}

# Last reading per printer, written by the Moonraker listener once per second (in this process)
# and served by GET /printers/{id}/telemetry/latest.
latest_readings: dict[int, dict] = {}
# Last bed geometry per printer (see geometry_from_status), for the live bed map.
latest_geometry: dict[int, dict] = {}


def geometry_from_status(status: dict) -> dict:
    """The bed as Klipper describes it: axis limits, the active bed mesh and the objects the file
    declared (exclude_object). Changes rarely: on homing, mesh calibration or a new print."""
    toolhead = status.get("toolhead") or {}
    mesh = status.get("bed_mesh") or {}
    exclude_object = status.get("exclude_object") or {}
    return {
        "axis_minimum": toolhead.get("axis_minimum"),
        "axis_maximum": toolhead.get("axis_maximum"),
        "bed_mesh": (
            {key: mesh.get(key) for key in ("profile_name", "mesh_min", "mesh_max", "probed_matrix")}
            if mesh.get("probed_matrix")
            else None
        ),
        "objects": exclude_object.get("objects") or [],
    }


def build_subscription(available_objects: Iterable[str] | None) -> dict[str, list[str] | None]:
    """The subscription for one printer: the core objects it has plus every optional sensor or
    fan it reports. Without the object list, the core set alone (Klipper skips unknown names)."""
    if available_objects is None:
        return dict(_CORE_SUBSCRIPTION)

    available = list(available_objects)
    subscription = {name: fields for name, fields in _CORE_SUBSCRIPTION.items() if name in available}
    for name in available:
        for prefix, fields in _PREFIXED_SUBSCRIPTION.items():
            if name.startswith(prefix):
                subscription[name] = list(fields)
    return subscription


def _number(value) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return round(float(value), 4)


def _component(vector, index: int) -> float | None:
    if isinstance(vector, (list, tuple)) and len(vector) > index:
        return _number(vector[index])
    return None


def _extra_sensors(status: dict) -> dict:
    extra = {}
    for name, values in status.items():
        prefix = next((prefix for prefix in _PREFIXED_SUBSCRIPTION if name.startswith(prefix)), None)
        if prefix is None or not isinstance(values, dict):
            continue
        for field in _PREFIXED_SUBSCRIPTION[prefix]:
            value = values.get(field)
            if isinstance(value, bool):
                extra[f"{name}.{field}"] = value
            elif (number := _number(value)) is not None:
                extra[f"{name}.{field}"] = number
    return extra


def sample_from_status(status: dict) -> dict:
    """One telemetry row from Klipper's merged status. A missing object gives None, never an
    error: which objects exist depends on the printer and its configuration."""
    print_stats = status.get("print_stats") or {}
    virtual_sdcard = status.get("virtual_sdcard") or {}
    motion = status.get("motion_report") or {}
    toolhead = status.get("toolhead") or {}
    gcode_move = status.get("gcode_move") or {}
    extruder = status.get("extruder") or {}
    bed = status.get("heater_bed") or {}

    # Creality reports the layer in virtual_sdcard and leaves print_stats.info null; upstream
    # Klipper is the other way around (when the slicer emits SET_PRINT_STATS_INFO).
    layer = virtual_sdcard.get("layer")
    if layer is None:
        layer = (print_stats.get("info") or {}).get("current_layer")
    # live_position is the head's estimated real position; toolhead.position runs ahead of it
    # (end of the last queued move), so it is only the fallback.
    position = motion.get("live_position") or toolhead.get("position")

    return {
        "layer_number": layer if isinstance(layer, int) and not isinstance(layer, bool) else None,
        "x": _component(position, 0),
        "y": _component(position, 1),
        "z": _component(position, 2),
        "velocity": _number(motion.get("live_velocity")),
        "extruder_velocity": _number(motion.get("live_extruder_velocity")),
        "extruder_temp": _number(extruder.get("temperature")),
        "extruder_target": _number(extruder.get("target")),
        "extruder_power": _number(extruder.get("power")),
        "bed_temp": _number(bed.get("temperature")),
        "bed_target": _number(bed.get("target")),
        "bed_power": _number(bed.get("power")),
        "fan_speed": _number((status.get("fan") or {}).get("speed")),
        "speed_factor": _number(gcode_move.get("speed_factor")),
        "extrude_factor": _number(gcode_move.get("extrude_factor")),
        "z_offset": _component(gcode_move.get("homing_origin"), 2),
        "progress": _number(virtual_sdcard.get("progress")),
        "filament_used": _number(print_stats.get("filament_used")),
        "extra": _extra_sensors(status) or None,
    }


def layer_snapshot(status: dict) -> dict:
    """What the printer was doing when a layer started, stored with the layer."""
    sample = sample_from_status(status)
    snapshot = {key: value for key, value in sample.items() if value is not None and key != "layer_number"}
    current_object = (status.get("exclude_object") or {}).get("current_object")
    if current_object:
        snapshot["current_object"] = current_object
    return snapshot


def clean_row(row: dict) -> dict:
    """Values read back from REAL columns carry float noise (25.11 comes back as
    25.110000610351562); four decimals is the precision the samples were stored with."""
    return {key: round(value, 4) if isinstance(value, float) else value for key, value in row.items()}


def downsample(points: list[dict], max_points: int) -> tuple[list[dict], float | None]:
    """Thins a job's series (dicts with "ts" plus SAMPLE_FIELDS and "extra", ordered by ts) to
    at most max_points by averaging fixed time buckets, so a chart of a 10 h print stays light.
    Cumulative fields keep the bucket's last value. Returns the points and the bucket width in
    seconds (None when the series was small enough to return as is)."""
    if len(points) <= max_points:
        return points, None

    start: datetime = points[0]["ts"]
    span = (points[-1]["ts"] - start).total_seconds()
    # max_points - 1 so the last point opens bucket number max_points - 1 at most.
    width = max(span / max(max_points - 1, 1), 1.0)

    buckets: list[list[dict]] = []
    current_index = None
    for point in points:
        index = int((point["ts"] - start).total_seconds() // width)
        if index != current_index:
            buckets.append([])
            current_index = index
        buckets[-1].append(point)

    return [_merge_bucket(bucket) for bucket in buckets], width


def _merge_bucket(bucket: list[dict]) -> dict:
    merged = {"ts": bucket[0]["ts"]}
    for field in SAMPLE_FIELDS:
        values = [point[field] for point in bucket if point.get(field) is not None]
        if not values:
            merged[field] = None
        elif field in _CUMULATIVE_FIELDS:
            merged[field] = values[-1]
        else:
            merged[field] = round(sum(values) / len(values), 4)

    extra_values: dict[str, list] = {}
    for point in bucket:
        for key, value in (point.get("extra") or {}).items():
            extra_values.setdefault(key, []).append(value)
    extra = {}
    for key, values in extra_values.items():
        numbers = [value for value in values if isinstance(value, (int, float)) and not isinstance(value, bool)]
        extra[key] = round(sum(numbers) / len(numbers), 4) if len(numbers) == len(values) else values[-1]
    merged["extra"] = extra or None
    return merged
