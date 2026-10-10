from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class DetectionCreate(BaseModel):
    # model_version_id is a column name, not one of pydantic's own model_* attributes.
    model_config = ConfigDict(protected_namespaces=())

    model_version_id: int
    has_defect: bool
    max_confidence: Decimal | None = Field(default=None, ge=0, le=1)
    defect_classes: list[str] = Field(default_factory=list)
    raw_output: dict


class DetectionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    id: int
    capture_id: int
    model_version_id: int
    has_defect: bool
    max_confidence: Decimal | None
    defect_classes: list
    raw_output: dict
    created_at: datetime
