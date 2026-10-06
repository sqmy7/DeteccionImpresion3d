from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class LayerCaptureCreate(BaseModel):
    camera_id: int
    image_path: str = Field(min_length=1, max_length=500)
    dominant_color_rgb: str | None = Field(default=None, max_length=7)


class LayerCaptureRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    layer_id: int
    camera_id: int
    image_path: str
    dominant_color_rgb: str | None
    captured_at: datetime
