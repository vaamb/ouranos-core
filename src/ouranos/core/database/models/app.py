from __future__ import annotations

from datetime import datetime, timezone
import enum
from enum import Enum, IntFlag, StrEnum
import re
from typing import Optional, Self, Sequence, TypedDict

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
import sqlalchemy as sa
from sqlalchemy import delete, insert, select, Table, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

import gaia_validators as gv
from gaia_validators import safe_enum_from_name

from ouranos import current_app
from ouranos.core.config.consts import (
    REGISTRATION_TOKEN_VALIDITY, TOKEN_SUBS)
from ouranos.core.database.models.abc import Base, ToDictMixin
from ouranos.core.database.models.types import UtcDateTime
from ouranos.core.database.utils import ArchiveLink
from ouranos.core.exceptions import DuplicatedEntry
from ouranos.core.utils import Tokenizer

argon2_hasher = PasswordHasher()


# ---------------------------------------------------------------------------
#   Users-related models, located in db_users
# ---------------------------------------------------------------------------
class Permission(IntFlag):
    VIEW = 1
    EDIT = 2
    OPERATE = 4
    ADMIN = 8


class RoleName(StrEnum):
    User = enum.auto()
    Operator = enum.auto()
    Administrator = enum.auto()
    Default = User


roles_definition: dict[RoleName, Permission] = {
    RoleName.User: Permission.VIEW | Permission.EDIT,
    RoleName.Operator: Permission.VIEW | Permission.EDIT | Permission.OPERATE,
    RoleName.Administrator: Permission.VIEW | Permission.EDIT |
                            Permission.OPERATE | Permission.ADMIN,
}


class Role(Base):
    __tablename__ = "roles"
    __bind_key__ = "app"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[RoleName] = mapped_column(unique=True)
    default: Mapped[bool] = mapped_column(default=False, index=True)
    permissions: Mapped[int] = mapped_column()

    # relationship
    users: Mapped[list["User"]] = relationship(back_populates="role")

    def __init__(self, **kwargs):
        super(Role, self).__init__(**kwargs)
        if self.permissions is None:
            self.permissions = 0

    @classmethod
    async def get(
            cls,
            session: AsyncSession,
            role_name: RoleName,
    ) -> Self | None:
        stmt = select(cls).where(cls.name == role_name)
        result = await session.execute(stmt)
        return result.scalars().one_or_none()

    @classmethod
    async def get_default(cls, session: AsyncSession) -> Self:
        stmt = select(cls).where(cls.default == True)
        result = await session.execute(stmt)
        return result.scalars().one()

    @classmethod
    async def insert_roles(cls, session: AsyncSession) -> None:
        stmt = select(cls)
        result = await session.execute(stmt)
        roles_in_db: list[Self] = result.scalars().all()
        roles = {role.name: role for role in roles_in_db}
        for name, permission in roles_definition.items():
            role = roles.get(name)
            if role is None:
                role = cls(name=name)
            role.reset_permissions()
            role.add_permission(permission)
            role.default = (role.name == RoleName.Default)
            session.add(role)

    def has_permission(self, perm: Permission) -> bool:
        return self.permissions & perm.value == perm.value

    def add_permission(self, perm: Permission) -> None:
        if not self.has_permission(perm):
            self.permissions += perm.value

    def remove_permission(self, perm: Permission) -> None:
        if self.has_permission(perm):
            self.permissions -= perm.value

    def reset_permissions(self) -> None:
        self.permissions = 0

    def __repr__(self) -> str:
        return f"<Role({self.name})>"


class UserMixin(ToDictMixin):
    id: int
    username: str | None
    role: Role | None
    firstname: str | None
    lastname: str | None
    active: bool

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

    def can(self, perm: Permission) -> bool:
        return self.role is not None and self.role.has_permission(perm)

    def check_password(self, password: str) -> bool:
        raise NotImplementedError


class AnonymousUser(UserMixin):
    id: int = -1
    username: str | None = None
    role: None = None
    firstname: str | None = None
    lastname: str | None = None
    active = False

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

    def check_password(self, password: str) -> bool:
        return False


anonymous_user = AnonymousUser()


AssociationUserRecap = Table(
    "association_user_recap",
    Base.metadata,
    sa.Column("user_uid",
              sa.Integer,
              sa.ForeignKey("users.id")),
    sa.Column("channel_id",
              sa.Integer,
              sa.ForeignKey("communication_channels.id")),
    info={"bind_key": "app"}
)


class UserTokenInfoDict(TypedDict):
    username: str | None
    firstname: str | None
    lastname: str | None
    role: RoleName | None
    email: str | None


class User(Base, UserMixin):
    __tablename__ = "users"
    __bind_key__ = "app"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(sa.String(64), index=True, unique=True)
    email: Mapped[str] = mapped_column(sa.String(64), index=True, unique=True)
    password_hash: Mapped[Optional[str]] = mapped_column(sa.String(128))
    role_id: Mapped[int] = mapped_column(sa.ForeignKey("roles.id"))

    # User account info fields
    active: Mapped[bool] = mapped_column(default=True)
    confirmed: Mapped[bool] = mapped_column(default=False)
    registration_datetime: Mapped[datetime] = mapped_column(
        UtcDateTime, default=func.current_timestamp())

    # User information fields
    firstname: Mapped[Optional[str]] = mapped_column(sa.String(64))
    lastname: Mapped[Optional[str]] = mapped_column(sa.String(64))
    last_seen: Mapped[datetime] = mapped_column(
        UtcDateTime, default=func.current_timestamp(), onupdate=func.current_timestamp())

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

    @property
    def role_name(self) -> RoleName:
        return self.role.name

    async def compute_default_role(
            self,
            session: AsyncSession,
            role_name: RoleName | str | None = None,
    ) -> Role:
        try:
            role_name = safe_enum_from_name(RoleName, role_name)
        except (TypeError, ValueError):
            role_name = None
        if role_name is not None:
            role = await Role.get(session, role_name)
            if role:
                return role
        admins: str | list = current_app.config.get("ADMINS", [])
        if isinstance(admins, str):
            admins = admins.split(",")
        if self.email in admins:
            return await Role.get(session, role_name=RoleName.Administrator)
        else:
            return await Role.get_default(session)

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
        user = cls(**kwargs)
        user.role = await user.compute_default_role(session, role_name)
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
        password = values.pop("password", None)
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
    async def get_multiple(
            cls,
            session: AsyncSession,
            registration_start_time: datetime | None = None,
            registration_end_time: datetime | None = None,
            confirmed: bool = False,
            active: bool = False,
            page: int = 0,
            per_page: int = 20,
    ) -> Sequence[Self]:
        start_page: int = page * per_page
        stmt = select(cls).offset(start_page).limit(per_page)
        if registration_start_time is not None:
            stmt = stmt.where(cls.registration_datetime >= registration_start_time)
        if registration_end_time is not None:
            stmt = stmt.where(registration_end_time >= cls.registration_datetime)
        if confirmed:
            stmt = stmt.where(cls.confirmed == True)
        if active:
            stmt = stmt.where(cls.active == True)
        result = await session.execute(stmt)
        return result.scalars().all()

    @classmethod
    async def insert_gaia(cls, session: AsyncSession) -> None:
        stmt = select(User).where(User.username == "Ouranos")
        result = await session.execute(stmt)
        gaia = result.scalars().first()
        if not gaia:
            stmt = select(Role).where(Role.name == RoleName.Administrator)
            result = await session.execute(stmt)
            admin: Role = result.scalars().one()
            gaia = cls(
                username="Ouranos",
                email="None",
                confirmed=True,
                role_id=admin.id,
            )
            session.add(gaia)

    def set_password(self, password: str) -> None:
        self.password_hash = argon2_hasher.hash(password)

    def check_password(self, password: str) -> bool:
        try:
            return argon2_hasher.verify(self.password_hash, password)
        except VerificationError:
            return False

    def validate_email(self, email_address: str) -> None:
        if re.match(r"^[\w-\.]+@([\w-]+\.)+[\w-]{2,4}$", email_address) is not None:
            self.email = email_address

    @staticmethod
    async def create_invitation_token(
            session: AsyncSession,
            role_name: RoleName | str | None = None,
            user_info: UserTokenInfoDict | None = None,
            expiration_delay: int = REGISTRATION_TOKEN_VALIDITY,
    ) -> str:
        user_info = user_info or {}
        if role_name:
            user_info["role"] = role_name
        role_name = user_info.pop("role", None)
        try:
            role_name = safe_enum_from_name(RoleName, role_name)
        except (TypeError, ValueError):
            role_name = None
        cor_role_name: RoleName | None = None
        if role_name is not None:
            default_role = await Role.get_default(session)
            role = await Role.get(session, role_name)
            if role is None:
                cor_role_name = None
            else:
                if role.name != default_role.name:
                    cor_role_name = role.name
        if cor_role_name is not None:
            user_info["role"] = cor_role_name.name
        if expiration_delay is None:
            expiration_delay = REGISTRATION_TOKEN_VALIDITY
        token = Tokenizer.create_token(
            subject=TOKEN_SUBS.REGISTRATION.value,
            expiration_delay=expiration_delay,
            other_claims=user_info,
        )
        return token


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
    "telegram",
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
class FlashMessage(Base):
    __tablename__ = "flash_message"
    __bind_key__ = "app"
    __archive_link__ = ArchiveLink("warnings", "recent")

    id: Mapped[int] = mapped_column(primary_key=True)
    level: Mapped[gv.WarningLevel] = mapped_column(default=gv.WarningLevel.low)
    title: Mapped[str] = mapped_column(sa.String(length=256))
    description: Mapped[Optional[str]] = mapped_column(sa.String(length=2048))
    created_on: Mapped[datetime] = mapped_column(UtcDateTime, default=func.current_timestamp())
    active: Mapped[bool] = mapped_column(default=True)

    @classmethod
    async def create(
            cls,
            session: AsyncSession,
            values: dict,
    ) -> None:
        stmt = insert(cls).values(values)
        await session.execute(stmt)

    @classmethod
    async def get_multiple(
            cls,
            session: AsyncSession,
            limit: int = 10,
    ) -> Sequence[Self]:
        stmt = (
            select(cls)
            .where(cls.active == True)
            .order_by(cls.created_on.desc(), cls.level)
            .limit(limit)
        )
        result = await session.execute(stmt)
        return result.scalars().all()

    @classmethod
    async def inactivate(
            cls,
            session: AsyncSession,
            message_id: int,
    ) -> None:
        stmt = (
            update(cls)
            .where(cls.id == message_id)
            .values({"active": False})
        )
        await session.execute(stmt)


class CalendarEvent(Base):
    __tablename__ = "calendar_events"
    __bind_key__ = "app"

    id: Mapped[int] = mapped_column(primary_key=True)
    level: Mapped[gv.WarningLevel] = mapped_column(default=gv.WarningLevel.low)
    title: Mapped[str] = mapped_column(sa.String(length=256))
    description: Mapped[Optional[str]] = mapped_column(sa.String(length=2048))
    created_on: Mapped[datetime] = mapped_column(UtcDateTime, default=func.current_timestamp())
    created_by: Mapped[str] = mapped_column(sa.ForeignKey("users.id"))
    start_time: Mapped[datetime] = mapped_column(UtcDateTime)
    end_time: Mapped[datetime] = mapped_column(UtcDateTime)
    active: Mapped[bool] = mapped_column(default=True)

    # relationship
    user: Mapped[list["User"]] = relationship(back_populates="calendar")

    @classmethod
    async def create(
            cls,
            session: AsyncSession,
            creator_id: int,
            values: dict,
    ) -> None:
        values["created_by"] = creator_id
        stmt = insert(cls).values(values)
        await session.execute(stmt)

    @classmethod
    async def get(
            cls,
            session: AsyncSession,
            event_id: int,
    ) -> Self | None:
        stmt = select(cls).where(cls.id == event_id)
        result = await session.execute(stmt)
        return result.scalars().one_or_none()

    @classmethod
    async def get_multiple(
            cls,
            session: AsyncSession,
            limit: int = 10,
    ) -> Sequence[Self]:
        stmt = (
            select(cls)
            .where(
                (cls.active == True)
                & (cls.end_time > datetime.now(tz=timezone.utc))
            )
            .order_by(cls.start_time.asc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        return result.scalars().all()

    @classmethod
    async def update(
            cls,
            session: AsyncSession,
            event_id: int,
            values: dict
    ) -> None:
        stmt = (
            update(cls)
            .where(cls.id == event_id)
            .values(values)
        )
        await session.execute(stmt)

    @classmethod
    async def inactivate(
            cls,
            session: AsyncSession,
            event_id: int,
    ) -> None:
        stmt = (
            update(cls)
            .where(cls.id == event_id)
            .values({"active": True})
        )
        await session.execute(stmt)


class GaiaJob(Base):
    __tablename__ = "gaia_jobs"
    __bind_key__ = "app"

    id: Mapped[int] = mapped_column(primary_key=True)
    command: Mapped[str] = mapped_column(sa.String(length=512))
    arguments: Mapped[str] = mapped_column(sa.String(length=512))
    done: Mapped[bool] = mapped_column(default=False)
