from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.db.models import CameraRole, CameraSourceType


class CameraBase(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    source_type: CameraSourceType
    source_uri: str = Field(min_length=1, max_length=255)
    role: CameraRole = CameraRole.primary
    roi: dict | None = None


class CameraCreate(CameraBase):
    pass


class CameraUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    source_type: CameraSourceType | None = None
    source_uri: str | None = Field(default=None, min_length=1, max_length=255)
    role: CameraRole | None = None
    roi: dict | None = None
    is_active: bool | None = None


class CameraRead(CameraBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    printer_id: int
    is_active: bool
    created_at: datetime
