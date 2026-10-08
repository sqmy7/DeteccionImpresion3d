from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.db.models import AlertSeverity, AlertStatus


class AlertCreate(BaseModel):
    severity: AlertSeverity


class AlertTransition(BaseModel):
    status: AlertStatus


class AlertRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    detection_id: int
    printer_id: int
    severity: AlertSeverity
    status: AlertStatus
    acknowledged_by: int | None
    acknowledged_at: datetime | None
    created_at: datetime


class AlertListItem(BaseModel):
    id: int
    detection_id: int
    printer_id: int
    printer_name: str
    severity: AlertSeverity
    status: AlertStatus
    acknowledged_by: int | None
    acknowledged_at: datetime | None
    created_at: datetime
    # Where it was raised; null only if the detection's layer is gone.
    print_job_id: int | None = None
    layer_number: int | None = None
    file_name: str | None = None
