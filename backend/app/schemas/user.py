from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.db.models import UserRole


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: str
    role: UserRole
    created_at: datetime
