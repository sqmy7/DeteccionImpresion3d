from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.db.models import IntegrationType, PrinterStatus


class PrinterBase(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    model: str | None = Field(default=None, max_length=100)
    octoprint_url: str = Field(max_length=255)
    integration_type: IntegrationType = IntegrationType.octoprint


class PrinterCreate(PrinterBase):
    # Optional: Moonraker needs no API key on the LAN, OctoPrint does.
    octoprint_api_key: str | None = Field(default=None, min_length=1)


class PrinterUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    model: str | None = Field(default=None, max_length=100)
    octoprint_url: str | None = Field(default=None, max_length=255)
    octoprint_api_key: str | None = Field(default=None, min_length=1)
    integration_type: IntegrationType | None = None


class PrinterRead(PrinterBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    last_known_status: PrinterStatus
    created_at: datetime
    updated_at: datetime
