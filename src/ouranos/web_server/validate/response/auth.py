from __future__ import annotations

from datetime import datetime

from ouranos.core.validate.base import BaseModel
from ouranos.web_server.validate.response.base import BaseResponse


class UserInfo(BaseModel):
    id: int = -1
    username: str | None = None
    firstname: str | None = None
    lastname: str | None = None
    permissions: int = 0
    is_authenticated: bool = False
    is_confirmed: bool = False


class LoginResponse(BaseResponse):
    user: UserInfo
    session_token: str
