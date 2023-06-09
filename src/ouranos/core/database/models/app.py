from __future__ import annotations

from datetime import datetime, timedelta, timezone
from enum import Enum, IntFlag
from hashlib import md5
import re
import time as ctime
from typing import Optional, Self, Sequence

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
import sqlalchemy as sa
from sqlalchemy import delete, insert, select, Table, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from ouranos import current_app
from ouranos.core.config.consts import (
    REGISTRATION_TOKEN_VALIDITY, SESSION_FRESHNESS, TOKEN_SUBS)
from ouranos.core.database import ArchiveLink
from ouranos.core.database.models.common import Base, BaseWarning, ToDictMixin
from ouranos.core.exceptions import DuplicatedEntry, NoResultFound
from ouranos.core.utils import ExpiredTokenError, InvalidTokenError, Tokenizer

argon2_hasher = PasswordHasher()


# ---------------------------------------------------------------------------
#   Users-related models, located in db_users
# ---------------------------------------------------------------------------
class Permission(IntFlag):
    VIEW = 1
    EDIT = 2
    OPERATE = 4
    ADMIN = 8


roles_definition = {
    "User": Permission.VIEW | Permission.EDIT,
    "Operator": Permission.VIEW | Permission.EDIT | Permission.OPERATE,
    "Administrator": Permission.VIEW | Permission.EDIT |
                     Permission.OPERATE | Permission.ADMIN,
}


class Role(Base):
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
        default_role = "User"
        stmt = select(Role)
        result = await session.execute(stmt)
        roles_in_db: list[Role] = result.scalars().all()
        roles = {role.name: role for role in roles_in_db}
        for name, permission in roles_definition.items():
            role = roles.get(name)
            if role is None:
                role = Role(name=name)
            role.reset_permissions()
            role.add_permission(permission)
            role.default = (role.name == default_role)
            session.add(role)

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
        return f"<Role({self.name})>"


class UserMixin(ToDictMixin):
    id: int
    username: str | None
    firstname: str | None
    lastname: str | None

    @property
    def is_confirmed(self) -> bool:
        raise NotImplementedError

    @property
    def is_authenticated(self) -> bool:
        raise NotImplementedError

    @property
    def is_anonymous(self) -> bool:
        raise NotImplementedError

    def get_id(self) -> int:
        try:
            return self.id
        except AttributeError:
            raise NotImplementedError("No `id` attribute - override `get_id`")

    def can(self, perm: int) -> bool:
        raise NotImplementedError


class AnonymousUser(UserMixin):
    id: int = -1
    username: str | None = None
    firstname: str | None = None
    lastname: str | None = None

    @property
    def is_confirmed(self) -> bool:
        return False

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


anonymous_user = AnonymousUser()


AssociationUserRecap = Table(
    "association_user_recap", Base.metadata,
    sa.Column("user_uid",
              sa.String(length=32),
              sa.ForeignKey("users.id")),
    sa.Column("channel_id",
              sa.Integer,
              sa.ForeignKey("communication_channels.id")),
)


class User(Base, UserMixin):
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
    registration_datetime: Mapped[datetime] = mapped_column(default=func.current_timestamp())

    # User information fields
    firstname: Mapped[Optional[str]] = mapped_column(sa.String(64))
    lastname: Mapped[Optional[str]] = mapped_column(sa.String(64))
    last_seen: Mapped[datetime] = mapped_column(default=func.current_timestamp(), onupdate=func.current_timestamp())

    # User notifications / services fields
    daily_recap: Mapped[bool] = mapped_column(default=False)
    telegram_id: Mapped[Optional[str]] = mapped_column(sa.String(16), unique=True)

    # relationship
    role: Mapped["Role"] = relationship(back_populates="users", lazy="selectin")
    recap_channels: Mapped[list["CommunicationChannel"]] = relationship(
        back_populates="users", secondary=AssociationUserRecap)
    calendar: Mapped[list["CalendarEvent"]] = relationship(back_populates="user")

    def __repr__(self):
        return f"<User({self.username}, role={self.role.name})>"

    @property
    def is_confirmed(self) -> bool:
        return self.confirmed

    @property
    def is_authenticated(self) -> bool:
        return True

    @property
    def is_anonymous(self) -> bool:
        return False

    @property
    def permissions(self) -> int:
        return self.role.permissions

    @classmethod
    async def create(
            cls,
            session: AsyncSession,
            username: str,
            password: str,
            **kwargs
    ) -> User:
        # Check if new user is a duplicate
        error = []
        stmt = select(User).where(User.username == username)
        if "email" in kwargs:
            stmt = stmt.where(User.email == kwargs["email"])
        if "telegram_id" in kwargs:
            stmt = stmt.where(User.telegram_id == kwargs["telegram_id"])
        result = await session.execute(stmt)
        previous_user: User = result.scalars().first()
        if previous_user:
            if previous_user.username == username:
                error.append("username")
            if previous_user.email == kwargs.get("email", False):
                error.append("email")
            if previous_user.telegram_id == kwargs.get("telegram_id", False):
                error.append("telegram_id")
            raise DuplicatedEntry(error)
        # Create user
        kwargs["username"] = username
        role_name = kwargs.pop("role", None)
        user = User(**kwargs)

        async def get_role(role_name: str | None = None) -> Role:
            if role_name is not None:
                stmt = select(Role).where(Role.name == role_name)
                result = await session.execute(stmt)
                role = result.scalars().first()
                if role:
                    return role
            admins: str | list = current_app.config.get("ADMINS", [])
            if isinstance(admins, str):
                admins = admins.split(",")
            if user.email in admins:
                stmt = select(Role).where(Role.name == "Administrator")
            else:
                stmt = select(Role).where(Role.default == True)  # noqa
            result = await session.execute(stmt)
            return result.scalars().first()
        if user.role is None:
            user.role = await get_role(role_name)
        user.set_password(password)
        session.add(user)
        await session.commit()
        return user

    @classmethod
    async def update(
            cls,
            session: AsyncSession,
            values: dict,
            user_id: int | str | None,
    ) -> None:
        user_id = user_id or values.pop("uid", None)
        if not user_id:
            raise ValueError(
                "Provide user_id either as a parameter or as a key in the updated info"
            )
        password = values.pop("password")
        stmt = (
            update(cls)
            .where(
                (User.id == user_id)
                | (User.username == user_id)
                | (User.email == user_id)
            )
            .values(**values)
        )
        await session.execute(stmt)
        user = await cls.get(session, user_id)
        if password:
            user.set_password(password)
        session.add(user)
        await session.commit()

    @classmethod
    async def delete(cls, session: AsyncSession, user_id: int | str) -> None:
        stmt = (
            delete(cls)
            .where(
                (cls.id == user_id)
                | (cls.username == user_id)
                | (cls.email == user_id)
            )
        )
        await session.execute(stmt)

    @classmethod
    async def get(
            cls,
            session: AsyncSession,
            user_id: int | str
    ) -> Self | None:
        stmt = (
            select(cls)
            .where(
                (cls.id == user_id)
                | (cls.username == user_id)
                | (cls.email == user_id)
            )
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @classmethod
    async def get_by_telegram_id(
            cls,
            session: AsyncSession,
            telegram_id: int
    ) -> Self:
        stmt = select(cls).where(cls.telegram_id == telegram_id)
        result = await session.execute(stmt)
        return result.scalars().one_or_none()

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
    async def create_invitation_token(
            session: AsyncSession,
            role_name: str | None = None,
    ) -> str:
        if role_name is not None:
            if role_name != "default":
                stmt = select(Role).where(Role.name == role_name)
                result = await session.execute(stmt)
                role = result.scalars().first()
                if role is None:
                    role_name = None
                else:
                    stmt = select(Role).where(Role.default == True)  # noqa
                    result = await session.execute(stmt)
                    default_role = result.scalars().one()
                    if role.name == default_role.name:
                        role_name = role.name
            else:
                role_name = None
        payload = {
            "sub": TOKEN_SUBS.REGISTRATION.value,
            "exp": datetime.now(timezone.utc) + timedelta(
                seconds=REGISTRATION_TOKEN_VALIDITY),
        }
        if role_name is not None:
            payload.update({"rle": role_name})
        return Tokenizer.dumps(payload)

    @staticmethod
    def load_from_token(token: str, token_use: str):
        # TODO: be explicit and use session
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


class ServiceLevel(Enum):
    all = "all"
    app = "app"
    ecosystem = "ecosystem"


services_definition = {
        "weather": ServiceLevel.app,
        "suntimes": ServiceLevel.app,
        "calendar": ServiceLevel.app
}


class Service(Base):
    __tablename__ = "services"
    __bind_key__ = "app"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(sa.String(length=16))
    level: Mapped[ServiceLevel] = mapped_column()
    status: Mapped[bool] = mapped_column(default=False)

    @classmethod
    async def insert_services(cls, session: AsyncSession) -> None:
        for name, level in services_definition.items():
            service_in_db = await cls.get(session, name)
            if service_in_db is None:
                service = cls(**{"name": name, "level": level})
                session.add(service)

    @classmethod
    async def create(
            cls,
            session: AsyncSession,
            values: dict | list[dict],
    ) -> None:
        stmt = insert(cls).values(values)
        await session.execute(stmt)

    @classmethod
    async def get(cls, session: AsyncSession, name: str) -> Self | None:
        stmt = select(cls).where(cls.name == name)
        result = await session.execute(stmt)
        return result.scalar()

    @classmethod
    async def get_multiple(
            cls,
            session: AsyncSession,
            level: ServiceLevel | list[ServiceLevel] | None = None
    ) -> Sequence[Service]:
        if level is ServiceLevel.all:
            level = None
        stmt = select(cls)
        if level:
            stmt = stmt.where(cls.level.in_(level))
        result = await session.execute(stmt)
        return result.scalars().all()


channels_definition = [
    "telegram"
]


class CommunicationChannel(Base):
    __tablename__ = "communication_channels"
    __bind_key__ = "app"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(sa.String(length=16))
    status: Mapped[bool] = mapped_column(default=False)

    # relationship
    users: Mapped[list["User"]] = relationship(back_populates="recap_channels",
                                               secondary=AssociationUserRecap)

    @classmethod
    async def get(cls, session: AsyncSession, name: str) -> Self | None:
        stmt = select(cls).where(cls.name == name)
        result = await session.execute(stmt)
        return result.scalar()

    @classmethod
    async def insert_channels(cls, session: AsyncSession):
        for channel in channels_definition:
            channel_in_db = await cls.get(session, channel)
            if channel_in_db is None:
                c = cls(name=channel)
                session.add(c)
        await session.commit()


# TODO: When problems solved, after x days: goes to archive
class FlashMessage(BaseWarning):
    __tablename__ = "flash_message"
    __bind_key__ = "app"
    __archive_link__ = ArchiveLink("warnings", "recent")


class CalendarEvent(Base):  # TODO: apply similar to warnings
    __tablename__ = "calendar_events"
    __bind_key__ = "app"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(sa.ForeignKey("users.id"))
    start_time: Mapped[datetime] = mapped_column()
    end_time: Mapped[datetime] = mapped_column()
    type: Mapped[int] = mapped_column()
    title: Mapped[str] = mapped_column(sa.String(length=256))
    description: Mapped[Optional[str]] = mapped_column(sa.String(length=2048))
    created_at: Mapped[datetime] = mapped_column(default=func.current_timestamp())
    updated_at: Mapped[Optional[datetime]] = mapped_column(onupdate=func.current_timestamp())
    active: Mapped[bool] = mapped_column(default=True)
    URL: Mapped[Optional[str]] = mapped_column(sa.String(length=1024))
    content: Mapped[Optional[str]] = mapped_column(sa.String(length=2048))

    # relationship
    user: Mapped[list["User"]] = relationship(back_populates="calendar")


class GaiaJob(Base):
    __tablename__ = "gaia_jobs"
    __bind_key__ = "app"

    id: Mapped[int] = mapped_column(primary_key=True)
    command: Mapped[str] = mapped_column(sa.String(length=512))
    arguments: Mapped[str] = mapped_column(sa.String(length=512))
    done: Mapped[bool] = mapped_column(default=False)
