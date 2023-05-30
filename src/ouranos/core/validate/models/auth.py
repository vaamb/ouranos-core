from __future__ import annotations

from datetime import datetime

from ouranos.core.validate.base import BaseModel
from ouranos.core.validate.models.common import BaseResponse


class UserInfo(BaseModel):
    id: int = -1
    username: str | None = None
    firstname: str | None = None
    lastname: str | None = None
    permissions: int = 0
    iat: datetime | None
    is_authenticated: bool = False
    is_confirmed: bool = False


class UserCreationPayload(BaseModel):
    username: str
    password: str
    email: str
    firstname: str | None = None
    lastname: str | None = None
    telegram_id: int | None = None


class LoginResponse(BaseResponse):
    user: UserInfo
    session_token: str
