from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ModelVersionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    file_path: str = Field(min_length=1, max_length=500)
    classes: list[str]
    metrics: dict | None = None
    trained_at: datetime | None = None


class ModelVersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    file_path: str
    classes: list
    metrics: dict | None
    trained_at: datetime | None
