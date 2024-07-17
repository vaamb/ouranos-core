from __future__ import annotations

from datetime import datetime

from ouranos.core.database.models.app import RoleName
from ouranos.core.validate.base import BaseModel


class UserDescription(BaseModel):
    username: str
    email: str
    role_name: RoleName
    firstname: str | None = None
    lastname: str | None = None
    confirmed: bool
    registration_datetime: datetime


class UserUpdatePayload(BaseModel):
    email: str | None = None
    firstname: str | None = None
    lastname: str | None = None
