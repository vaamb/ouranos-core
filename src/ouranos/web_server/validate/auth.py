from __future__ import annotations

from datetime import datetime

from gaia_validators import MissingValue, missing

from ouranos.core.database.models.app import RoleName
from ouranos.core.validate.base import BaseModel


class UserInvitationPayload(BaseModel):
    username: str | MissingValue = missing
    firstname: str | None | MissingValue = missing
    lastname: str | None | MissingValue = missing
    role: RoleName | str | None | MissingValue = missing
    email: str | MissingValue = missing


class UserCreationPayload(BaseModel):
    username: str
    password: str
    email: str
    firstname: str | None = None
    lastname: str | None = None
    telegram_id: int | None = None


class UserInfo(BaseModel):
    id: int = -1
    username: str | None = None
    firstname: str | None = None
    lastname: str | None = None
    permissions: int = 0
    is_authenticated: bool = False
    is_confirmed: bool = False
    last_seen: datetime | None = None


class LoginInfo(BaseModel):
    msg: str
    user: UserInfo
    session_token: str


class UserPasswordUpdatePayload(BaseModel):
    password: str
