from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class LayerCreate(BaseModel):
    layer_number: int = Field(ge=0)
    z_height: Decimal = Field(ge=0)


class LayerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    job_id: int
    layer_number: int
    z_height: Decimal
    detected_at: datetime
