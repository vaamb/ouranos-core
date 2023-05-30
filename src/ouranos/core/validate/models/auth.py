from __future__ import annotations

from datetime import datetime, timedelta

from pydantic import BaseModel as _BaseModel

from ouranos.core.config.consts import SESSION_FRESHNESS
from ouranos.core.database.models import Permission, User
from ouranos.core.validate.models.common import simple_message


class BaseModel(_BaseModel):
    class Config:
        orm_mode = True


class CurrentUser(BaseModel):
    id: int
    username: str | None
    firstname: str | None
    lastname: str | None
    permissions: int
    iat: datetime | None
    is_authenticated: bool = False
    is_anonymous: bool = True
    is_confirmed: bool = False

    @classmethod
    def from_user(cls, user: User | None):
        if user is None:
            return anonymous_user
        return cls(
            id=user.id,
            username=user.username,
            firstname=user.firstname,
            lastname=user.lastname,
            permissions=user.role.permissions,
            iat=datetime.utcnow().replace(microsecond=0),
            is_confirmed=user.confirmed,
        )

    def is_fresh(self) -> bool:
        if self.iat is None:
            return False
        time_limit = datetime.utcnow().replace(microsecond=0) - timedelta(seconds=SESSION_FRESHNESS)
        return self.iat < time_limit

    def can(self, perm: Permission) -> bool:
        return self.permissions & perm.value == perm.value


class AuthenticatedUser(CurrentUser):
    username: str

    is_authenticated: bool = True
    is_anonymous: bool = False


class AnonymousUser(CurrentUser):
    id: int = -1
    username: None = None
    permissions = 0

    def can(self, perm: Permission) -> bool:
        return False


anonymous_user = AnonymousUser()


class user_creation(BaseModel):
    username: str
    firstname: str | None = None
    lastname: str | None = None
    email: str
    telegram_id: int | None = None
    password: str


class login_response(simple_message):
    user: AuthenticatedUser
    session_token: str
