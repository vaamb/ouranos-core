from __future__ import annotations

from datetime import datetime

from gaia_validators import MissingValue, missing

from ouranos.core.database.models.app import RoleName
from ouranos.core.validate.base import BaseModel


class UserDescription(BaseModel):
    username: str
    email: str
    role_name: RoleName
    firstname: str | None = None
    lastname: str | None = None
    created_at: datetime
    confirmed_at: datetime | None
    last_seen: datetime


class UserUpdatePayload(BaseModel):
    firstname: str | None | MissingValue = missing
    lastname: str | None | MissingValue = missing
