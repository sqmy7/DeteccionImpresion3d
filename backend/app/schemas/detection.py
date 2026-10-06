from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class DetectionCreate(BaseModel):
    model_version_id: int
    has_defect: bool
    max_confidence: Decimal | None = Field(default=None, ge=0, le=1)
    defect_classes: list[str] = Field(default_factory=list)
    raw_output: dict


class DetectionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    capture_id: int
    model_version_id: int
    has_defect: bool
    max_confidence: Decimal | None
    defect_classes: list
    raw_output: dict
    created_at: datetime
