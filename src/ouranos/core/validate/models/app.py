from __future__ import annotations

from pydantic import BaseModel, create_model


class user_creation(BaseModel):
    username: str
    password: str
    email: str
    telegram_id: int | None = None
    firstname: str | None = None
    lastname: str | None = None
    role: str | None = None


class user(BaseModel):
    username: str | None
    firstname: str | None
    lastname: str | None
    permissions: int

    is_authenticated: bool
    is_anonymous: bool
    get_id: int | None
    can: bool

    def to_dict(self) -> dict:
        pass


class login_response(BaseModel):
    msg: str
    data: create_model("data", user=(dict, user))
