from __future__ import annotations

from datetime import datetime, timezone
from enum import IntFlag
from hashlib import md5
import re
import time as ctime
from typing import Optional

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
import sqlalchemy as sa
from sqlalchemy import select, Table
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.ext.asyncio import AsyncSession

from ouranos import current_app, db
from ouranos.core.database import ArchiveLink
from ouranos.core.database.models.common import BaseWarning
from ouranos.core.utils import ExpiredTokenError, InvalidTokenError, Tokenizer

argon2_hasher = PasswordHasher()
base = db.Model


# ---------------------------------------------------------------------------
#   Users-related models, located in db_users
# ---------------------------------------------------------------------------
class Permission(IntFlag):
    VIEW = 1
    EDIT = 2
    OPERATE = 4
    ADMIN = 8


class Role(base):
    __tablename__ = "roles"
    __bind_key__ = "app"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(sa.String(64), unique=True)
    default: Mapped[bool] = mapped_column(default=False, index=True)
    permissions: Mapped[int] = mapped_column()

    # relationship
    users: Mapped[list["User"]] = relationship(back_populates="role")

    def __init__(self, **kwargs):
        super(Role, self).__init__(**kwargs)
        if self.permissions is None:
            self.permissions = 0

    @staticmethod
    async def insert_roles(session: AsyncSession):
        roles_defined = {
            "User": Permission.VIEW | Permission.EDIT,
            "Operator": Permission.VIEW | Permission.EDIT | Permission.OPERATE,
            "Administrator": Permission.VIEW | Permission.EDIT |
                             Permission.OPERATE | Permission.ADMIN,
        }
        default_role = "User"
        stmt = select(Role)
        result = await session.execute(stmt)
        roles_in_db: list[Role] = result.scalars().all()
        roles = {role.name: role for role in roles_in_db}
        for name, permission in roles_defined.items():
            role = roles.get(name)
            if role is None:
                role = Role(name=name)
            role.reset_permissions()
            role.add_permission(permission)
            role.default = (role.name == default_role)
            session.add(role)
        await session.commit()

    def has_permission(self, perm: Permission):
        return self.permissions & perm.value == perm.value

    def add_permission(self, perm: Permission):
        if not self.has_permission(perm):
            self.permissions += perm.value

    def remove_permission(self, perm: Permission):
        if self.has_permission(perm):
            self.permissions -= perm.value

    def reset_permissions(self):
        self.permissions = 0

    def __repr__(self):
        return f"<Role {self.name}>"


class UserMixin:
    id: int = 0
    username: str = ""
    firstname: str = ""
    is_fresh: bool = False

    @property
    def is_authenticated(self) -> bool:
        return True

    @property
    def is_anonymous(self) -> bool:
        return False

    def get_id(self) -> int:
        try:
            return self.id
        except AttributeError:
            raise NotImplementedError("No `id` attribute - override `get_id`")

    def can(self, perm: int) -> bool:
        raise NotImplementedError

    def to_dict(self) -> dict:
        raise NotImplementedError


class AnonymousUserMixin(UserMixin):
    @property
    def is_authenticated(self) -> bool:
        return False

    @property
    def is_anonymous(self) -> bool:
        return True

    def get_id(self) -> None:
        return

    def can(self, perm) -> bool:
        return False

    def to_dict(self) -> dict:
        return {
            "username": "",
            "firstname": "",
            "lastname": "",
            "permissions": 0,
        }


anonymous_user = AnonymousUserMixin()


AssociationUserRecap = Table(
    "association_user_recap", base.metadata,
    sa.Column("user_uid",
              sa.String(length=32),
              sa.ForeignKey("users.id")),
    sa.Column("channel_id",
              sa.Integer,
              sa.ForeignKey("communication_channels.id")),
)


class User(base, UserMixin):
    __tablename__ = "users"
    __bind_key__ = "app"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(sa.String(64), index=True, unique=True)
    email: Mapped[str] = mapped_column(sa.String(120), index=True, unique=True)

    # User authentication fields
    password_hash: Mapped[Optional[str]] = mapped_column(sa.String(128))
    confirmed: Mapped[bool] = mapped_column(default=False)
    role_id: Mapped[int] = mapped_column(sa.ForeignKey("roles.id"))

    # User registration fields
    token: Mapped[Optional[str]] = mapped_column(sa.String(32))
    registration_datetime: Mapped[datetime] = mapped_column(default=datetime.now(timezone.utc))

    # User information fields
    firstname: Mapped[Optional[str]] = mapped_column(sa.String(64))
    lastname: Mapped[Optional[str]] = mapped_column(sa.String(64))
    last_seen: Mapped[datetime] = mapped_column(default=datetime.now(timezone.utc))

    # User notifications / services fields
    daily_recap: Mapped[bool] = mapped_column(default=False)
    telegram_chat_id: Mapped[Optional[str]] = mapped_column(sa.String(16), unique=True)

    # relationship
    role: Mapped["Role"] = relationship(back_populates="users")
    recap_channels: Mapped[list["CommunicationChannel"]] = relationship(back_populates="users",
                                                                         secondary=AssociationUserRecap)
    calendar: Mapped[list["CalendarEvent"]] = relationship(back_populates="user")

    @classmethod
    async def create(cls, session: AsyncSession, **kwargs):
        user = User(**kwargs)
        if user.role is None:
            admins: str | list = current_app.config.get("ADMINS", [])
            if isinstance(admins, str):
                admins = admins.split(",")
            if user.email in admins:
                stmt = select(Role).where(Role.name == "Administrator")
            else:
                stmt = select(Role).where(Role.default is True)
            result = await session.execute(stmt)
            user.role = result.scalars().first()
        return user

    @staticmethod
    async def insert_gaia(session: AsyncSession):
        stmt = select(User).where(User.username == "Ouranos")
        result = await session.execute(stmt)
        gaia = result.scalars().first()
        if not gaia:
            stmt = select(Role).where(Role.name == "Administrator")
            result = await session.execute(stmt)
            admin = result.scalars().first()
            gaia = User(
                username="Ouranos",
                email="None",
                confirmed=True,
                role=admin
            )
            session.add(gaia)
            await session.commit()

    def set_password(self, password: str):
        self.password_hash = argon2_hasher.hash(password)

    def check_password(self, password):
        try:
            return argon2_hasher.verify(self.password_hash, password)
        except VerificationError:
            return False

    def validate_email(self, email_address: str):
        if re.match(r"^[\w-\.]+@([\w-]+\.)+[\w-]{2,4}$", email_address) is not None:
            self.email = email_address

    def can(self, perm: Permission):
        return self.role is not None and self.role.has_permission(perm)

    def avatar(self, size):
        digest = md5(
            self.email.lower().encode("utf-8"), usedforsecurity=False
        ).hexdigest()
        return f"https://www.gravatar.com/avatar/{digest}?d=identicon&s={size}"

    def create_token(
            self,
            payload: dict,
            secret_key: str = None,
            expires_in: int = 1800,
            **kwargs
    ) -> str:
        payload.update({"user_id": self.id})
        if expires_in:
            payload.update({"exp": ctime.time() + expires_in})
        for key, value in kwargs.items():
            if value:
                payload.update(**kwargs)
        return Tokenizer.dumps(payload, secret_key)

    @staticmethod
    def load_from_token(token: str, token_use: str):
        try:
            payload = Tokenizer.loads(token)
        except (ExpiredTokenError, InvalidTokenError):
            return None
        if payload.get("use") != token_use:
            return
        user_id = payload.get("user_id", 0)
        return User.query.get(user_id)

    @staticmethod
    def token_can(token: str, perm: int, usage: str = None) -> bool:
        user = User.load_from_token(token, usage)
        if user:
            return user.can(perm)
        return False

    def to_dict(self, complete=False) -> dict:
        rv = {
            "username": self.username,
            "firstname": self.firstname,
            "lastname": self.lastname,
            "permissions": self.role.permissions,
        }
        if complete:
            rv.update({
                "email": self.email,
                "last_seen": self.last_seen,
                "registration": self.registration_datetime,
                # TODO: change var name
                "daily_recap": self.daily_recap,
                "telegram_chat_id": self.telegram_chat_id,
            })
        return rv


class Service(base):
    __tablename__ = "services"
    __bind_key__ = "app"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(sa.String(length=16))
    level: Mapped[str] = mapped_column(sa.String(length=4))
    status: Mapped[bool] = mapped_column(default=False)

    def to_dict(self):
        return {
            "name": self.name,
            "level": self.level,
            "status": self.status,
        }


class CommunicationChannel(base):
    __tablename__ = "communication_channels"
    __bind_key__ = "app"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(sa.String(length=16))
    status: Mapped[bool] = mapped_column(default=False)

    # relationship
    users: Mapped[list["User"]] = relationship(back_populates="recap_channels",
                                               secondary=AssociationUserRecap)

    @staticmethod
    async def insert_channels(session: AsyncSession):
        channels = ["telegram"]
        stmt = select(CommunicationChannel)
        result = await session.execute(stmt)
        channels_in_db = result.scalars().all()
        for c in channels:
            channel = None
            for channel_in_db in channels_in_db:
                if channel_in_db.name == c:
                    channel = channel_in_db
                    break
            if channel is None:
                channel = CommunicationChannel(name=c)
            session.add(channel)
        await session.commit()


# TODO: When problems solved, after x days: goes to archive
class FlashMessage(BaseWarning):
    __tablename__ = "flash_message"
    __bind_key__ = "app"
    __archive_link__ = ArchiveLink("warnings", "recent")


class CalendarEvent(base):  # TODO: apply similar to warnings
    __tablename__ = "calendar_events"
    __bind_key__ = "app"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(sa.ForeignKey("users.id"))
    start_time: Mapped[datetime] = mapped_column()
    end_time: Mapped[datetime] = mapped_column()
    type: Mapped[int] = mapped_column()
    title: Mapped[str] = mapped_column(sa.String(length=256))
    description: Mapped[Optional[str]] = mapped_column(sa.String(length=2048))
    created_at: Mapped[datetime] = mapped_column()
    updated_at: Mapped[Optional[datetime]] = mapped_column()
    active: Mapped[bool] = mapped_column(default=True)
    URL: Mapped[Optional[str]] = mapped_column(sa.String(length=1024))
    content: Mapped[Optional[str]] = mapped_column(sa.String(length=2048))

    # relationship
    user: Mapped[list["User"]] = relationship(back_populates="calendar")


class GaiaJob(base):
    __tablename__ = "gaia_jobs"
    __bind_key__ = "app"

    id: Mapped[int] = mapped_column(primary_key=True)
    command: Mapped[str] = mapped_column(sa.String(length=512))
    arguments: Mapped[str] = mapped_column(sa.String(length=512))
    done: Mapped[bool] = mapped_column(default=False)
