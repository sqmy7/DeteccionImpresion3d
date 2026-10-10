from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class TelemetryPoint(BaseModel):
    ts: datetime
    layer_number: int | None = None
    x: float | None = None
    y: float | None = None
    z: float | None = None
    velocity: float | None = None
    extruder_velocity: float | None = None
    extruder_temp: float | None = None
    extruder_target: float | None = None
    extruder_power: float | None = None
    bed_temp: float | None = None
    bed_target: float | None = None
    bed_power: float | None = None
    fan_speed: float | None = None
    speed_factor: float | None = None
    extrude_factor: float | None = None
    z_offset: float | None = None
    progress: float | None = None
    filament_used: float | None = None
    extra: dict[str, Any] | None = None


class JobTelemetryRead(BaseModel):
    job_id: int
    samples: int
    # Width of the averaging buckets when the series was thinned for the chart; None = raw.
    bucket_seconds: float | None
    points: list[TelemetryPoint]


class PrinterEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    printer_id: int
    print_job_id: int | None
    ts: datetime
    klipper_eventtime: float | None
    event_type: str
    field: str | None
    value_before: Any
    value_after: Any
    origin: str
    detail: dict[str, Any] | None
    hash: str


class ChainVerificationRead(BaseModel):
    ok: bool
    events_checked: int
    first_broken_id: int | None
    reason: str | None
    last_hash: str | None
