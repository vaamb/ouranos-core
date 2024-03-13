from __future__ import annotations

from ouranos.core.validate.base import BaseModel
from ouranos.web_server.validate.response.base import BaseResponse


class UserCreationPayload(BaseModel):
    username: str
    password: str
    email: str
    firstname: str | None = None
    lastname: str | None = None
    telegram_id: int | None = None


class UserInfoResponse(BaseModel):
    id: int = -1
    username: str | None = None
    firstname: str | None = None
    lastname: str | None = None
    permissions: int = 0
    is_authenticated: bool = False
    is_confirmed: bool = False


class LoginResponse(BaseResponse):
    user: UserInfoResponse
    session_token: str
