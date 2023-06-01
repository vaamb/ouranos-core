from __future__ import annotations

from ouranos.core.validate.base import BaseModel


class UserPayload(BaseModel):
    username: str
    password: str
    email: str
    firstname: str | None = None
    lastname: str | None = None
    telegram_id: int | None = None
