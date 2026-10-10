from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class IncidentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    print_job_id: int
    printer_id: int
    camera_id: int | None
    opened_at: datetime
    reason: str
    mode: str | None
    defect_class: str
    streak: list[dict[str, Any]]
    detection_id: int | None
    first_defect_at: datetime | None
    announced_at: datetime | None
    pause_sent_at: datetime | None
    paused_at: datetime | None
    status: str
    outcome: str | None
    decided_by: str | None
    decided_at: datetime | None
    label: str
    labeled_by: str | None
    labeled_at: datetime | None
    telemetry_snapshot: dict[str, Any] | None
    detail: dict[str, Any] | None
    updated_at: datetime
    # Filled in by the API, not stored:
    job_file_name: str | None = None
    # From the first photo with the defect to Klipper confirming "paused" (docs/META_FINAL.md a.2).
    seconds_to_pause: float | None = None


class BoxOnFrame(BaseModel):
    class_name: str
    confidence: float
    x1: float
    y1: float
    x2: float
    y2: float


class IncidentDetection(BaseModel):
    detection_id: int
    capture_id: int
    layer_number: int
    z_height: float | None
    captured_at: datetime | None
    # What the incident's class scored in this photo, and every box the model drew (normalized to the full frame).
    confidence: float | None
    image_url: str
    boxes: list[BoxOnFrame]


class IncidentDetail(IncidentRead):
    job: dict[str, Any]
    detections: list[IncidentDetection]
    events: list[dict[str, Any]]
    chain: dict[str, Any]
    report_url: str
    # The sample of the job closest to the moment Klipper paused, when it did.
    telemetry_at_pause: dict[str, Any] | None = None


class IncidentLabel(BaseModel):
    label: Literal["correct", "false_positive", "unlabeled"]
