from __future__ import annotations

from datetime import datetime, timezone
import enum
from enum import IntFlag, StrEnum
import re
from typing import Optional, Self, Sequence, TypedDict

from anyio import Path as ioPath
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
import sqlalchemy as sa
from sqlalchemy import delete, insert, or_, select, Table, UniqueConstraint, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

import gaia_validators as gv
from gaia_validators import safe_enum_from_name

from ouranos import current_app
from ouranos.core.config.consts import (
    REGISTRATION_TOKEN_VALIDITY, TOKEN_SUBS)
from ouranos.core.database.models.abc import Base, CRUDMixin, ToDictMixin
from ouranos.core.database.models.caches import cache_users
from ouranos.core.database.models.types import PathType, UtcDateTime
from ouranos.core.database.utils import ArchiveLink
from ouranos.core.utils import Tokenizer

argon2_hasher = PasswordHasher()


class _UnfilledCls:
    pass


_Unfilled = _UnfilledCls()


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

    # ---------------------------------------------------------------------------
    #   Methods to override the Mixin default
    # ---------------------------------------------------------------------------
    def __repr__(self):
        return f"<User({self.username}, role={self.role.name.name})>"

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

    def check_password(self, password: str) -> bool:
        try:
            return argon2_hasher.verify(self.password_hash, password)
        except VerificationError:
            return False

    # ---------------------------------------------------------------------------
    #   Tokens creation
    # ---------------------------------------------------------------------------
    @classmethod
    async def create_invitation_token(
            cls,
            session: AsyncSession,
            user_info: UserTokenInfoDict | None = None,
            expiration_delay: int = REGISTRATION_TOKEN_VALIDITY,
    ) -> str:
        user_info = user_info or {}
        expiration_delay = expiration_delay or REGISTRATION_TOKEN_VALIDITY
        # Get the required role name
        role_name = user_info.pop("role", None)
        role = await cls._compute_default_role(session, role_name=role_name)
        default_role = await Role.get_default(session)
        if role.name != default_role.name:
            user_info["role"] = role.name.name
        # Create the token
        token = Tokenizer.create_token(
            subject=TOKEN_SUBS.REGISTRATION.value,
            expiration_delay=expiration_delay,
            other_claims=user_info,
        )
        return token

    # ---------------------------------------------------------------------------
    #   Methods involved in the data processing of user creation and update
    # ---------------------------------------------------------------------------
    @classmethod
    def _validate_email(cls, email_address: str) -> None:
        # Oversimplified but ok
        regex = r"^[\-\w\.]+@([\w\-]+\.)+[\w\-]{2,4}$"
        if re.match(regex, email_address) is None:
            raise ValueError("Wrong email format.")

    @classmethod
    def _validate_password(cls, password: str) -> None:
        # At least one lowercase, one capital letter, one number, one special char,
        #  and no space
        regex = r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[-+_!$&?.,])(?=.{8,})[^ ]+$"
        if re.match(regex, password) is None:
            raise ValueError("Wrong password format.")

    @classmethod
    async def _validate_values_payload(
            cls,
            session: AsyncSession,
            /,
            values: dict,
    ) -> None:
        errors = []
        # Check if the email is valid
        if "email" in values:
            try:
                cls._validate_email(values["email"])
            except ValueError as e:
                errors.extend(e.args)
        # Check if password has the proper format
        if "password" in values:
            try:
                cls._validate_password(values["password"])
            except ValueError as e:
                errors.extend(e.args)
        # Check if some of the info provided are already used
        previous_user: User = await cls.get_by(
            session,
            username=values.get("username", None),
            email=values.get("email", None),
            telegram_id=values.get("telegram_id", None),
        )
        if previous_user is not None:
            if "username" in values and previous_user.email == values["username"]:
                errors.append("Username already used.")
            if "email" in values and previous_user.email == values["email"]:
                errors.append("Email address already used.")
            if "telegram_id" in values and previous_user.telegram_id == values["telegram_id"]:
                errors.append("Telegram id address already used.")
        if errors:
            raise ValueError(errors)

    @classmethod
    def _generate_password_hash(cls, password: str) -> str:
        if password is None:
            raise ValueError("password cannot be `None`")
        return argon2_hasher.hash(password)

    @classmethod
    async def _compute_default_role(
            cls,
            session: AsyncSession,
            role_name: RoleName | str | None = None,
            email: str | None = None,
    ) -> Role:
        # Promote to admin if the email address is in the admin mail list
        admins: str | list = current_app.config.get("ADMINS", [])
        if isinstance(admins, str):
            admins = admins.split(",")
        if email is not None and email in admins:
            return await Role.get(session, role_name=RoleName.Administrator)
        # Try to get the role name
        try:
            role_name = safe_enum_from_name(RoleName, role_name)
        except (TypeError, ValueError):
            role_name = None
        # Get required role
        if role_name is not None:
            role = await Role.get(session, role_name)
            if role:
                return role
        return await Role.get_default(session)

    @classmethod
    async def _update_values_payload(
            cls,
            session: AsyncSession,
            /,
            values: dict,
    ) -> dict[str, str]:
        password = values.pop("password", None)
        if password is not None:
            values["password_hash"] = cls._generate_password_hash(password)
        role_name = values.pop("role", _Unfilled)
        if role_name is not _Unfilled:
            email = values.get("email", None)
            role = await cls._compute_default_role(session, role_name, email)
            values["role_id"] = role.id
        return values

    # ---------------------------------------------------------------------------
    #   CRUD methods
    # ---------------------------------------------------------------------------
    @classmethod
    async def create(
            cls,
            session: AsyncSession,
            /,
            values: dict,
    ) -> None:
        # Check we have a username, password and email
        if not (
            "username" in values
            and "password" in values
            and "email" in values
        ):
            raise ValueError(
                "`username`, `password` and `email` need to be passed in the values."
            )
        # Validate the values payload
        await cls._validate_values_payload(session, values)
        # Update the payload values for the password and role_id
        if "role" not in values:
            # If role is None, the default role will be assigned
            values["role"] = None
        values = await cls._update_values_payload(session, values)
        # Create user
        stmt = insert(cls).values(**values)
        await session.execute(stmt)

    @classmethod
    async def get(
            cls,
            session: AsyncSession,
            user_id: int,
    ) -> Self | None:
        try:
            return cache_users[user_id]
        except KeyError:
            stmt = (
                select(cls)
                .where(cls.id == user_id)
            )
            result = await session.execute(stmt)
            user = result.scalar_one_or_none()
            cache_users[user_id] = user
            session.expunge(user)
            session.expunge(user.role)
            return user

    @classmethod
    async def get_by(
            cls,
            session,
            /,
            **lookup_keys: str | int | None,
    ) -> Self | None:
        non_null_lookup_keys = {
            key: value
            for key, value in lookup_keys.items()
            if value is not None
        }
        if not non_null_lookup_keys:
            return None
        stmt = (
            select(cls)
            .where(
                or_(
                    cls.__table__.c[key] == value
                    for key, value in non_null_lookup_keys.items()
                )
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
    async def update(
            cls,
            session: AsyncSession,
            /,
            user_id: int,
            values: dict,
    ) -> None:
        # Validate the values payload
        await cls._validate_values_payload(session, values=values)
        # Update the payload values for the password and role_id
        values = await cls._update_values_payload(session, values=values)
        # Update the user
        stmt = (
            update(cls)
            .where(cls.id == user_id)
            .values(**values)
        )
        await session.execute(stmt)
        cache_users.pop(user_id, None)

    @classmethod
    async def delete(
            cls,
            session: AsyncSession,
            /,
            user_id: int,
    ) -> None:
        stmt = (
            delete(cls)
            .where(cls.id == user_id)
        )
        await session.execute(stmt)

    @classmethod
    async def insert_gaia(cls, session: AsyncSession) -> None:
        gaia = await cls.get_by(session, username="Ouranos")
        if gaia is None:
            admin = await Role.get(session, role_name=RoleName.Administrator)
            stmt = (
                insert(cls)
                .values({
                    "username": "Ouranos",
                    "email": "None",
                    "confirmed": True,
                    "role_id": admin.id,
                })
            )
            await session.execute(stmt)


class ServiceLevel(StrEnum):
    all = "all"
    app = "app"
    ecosystem = "ecosystem"


class ServiceName(StrEnum):
    weather = "weather"
    suntimes = "suntimes"
    calendar = "calendar"
    wiki = "wiki"


services_definition: dict[ServiceName, ServiceLevel] = {
        ServiceName.weather: ServiceLevel.app,
        ServiceName.calendar: ServiceLevel.app,
        ServiceName.wiki: ServiceLevel.app,
}


class Service(Base, CRUDMixin):
    __tablename__ = "services"
    __bind_key__ = "app"
    _lookup_keys = ["name"]

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[ServiceName] = mapped_column(sa.String(length=16), unique=True)
    level: Mapped[ServiceLevel] = mapped_column()
    status: Mapped[bool] = mapped_column(default=False)

    @classmethod
    async def insert_services(cls, session: AsyncSession) -> None:
        for name, level in services_definition.items():
            service = await cls.get(session, name=name)
            if service is None:
                await cls.create(session, name=name, values={"level": level})


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
            *,
            start_time: datetime | None = None,
            end_time: datetime | None = None,
            limit: int | None = None,
    ) -> Sequence[Self]:
        stmt = (
            select(cls)
            .where(
                (cls.active == True)
            )
            .order_by(cls.start_time.asc())
        )
        if start_time is not None:
            stmt = stmt.where(
                (cls.start_time >= start_time)
                | (cls.end_time >= start_time)
            )
        if end_time is not None:
            stmt = stmt.where(
                (cls.start_time <= end_time)
                | (cls.end_time <= end_time)
            )
        if limit is not None:
            stmt = stmt.limit(limit)
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
            .values({"active": False})
        )
        await session.execute(stmt)


class GaiaJob(Base):
    __tablename__ = "gaia_jobs"
    __bind_key__ = "app"

    id: Mapped[int] = mapped_column(primary_key=True)
    command: Mapped[str] = mapped_column(sa.String(length=512))
    arguments: Mapped[str] = mapped_column(sa.String(length=512))
    done: Mapped[bool] = mapped_column(default=False)


# ---------------------------------------------------------------------------
#   Wiki topics and articles
# ---------------------------------------------------------------------------
class WikiArticleNotFound(KeyError):
    pass


class ModificationType(StrEnum):
    creation = enum.auto()
    deletion = enum.auto()
    update = enum.auto()


class WikiObject:
    @staticmethod
    def root_dir() -> ioPath:
        return ioPath(current_app.static_dir)

    @staticmethod
    def wiki_dir() -> ioPath:
        return ioPath(current_app.wiki_dir)

    @classmethod
    def get_rel_path(cls, abs_path: ioPath) -> ioPath:
        return abs_path.relative_to(cls.root_dir())


class WikiTopic(Base, WikiObject):
    __tablename__ = "wiki_topics"
    __bind_key__ = "app"
    __table_args__ = (
        UniqueConstraint(
            "name",
            name="uq_wiki_topics_name"
        ),
    )
    _lookup_keys = ["name"]

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(sa.String(length=64), unique=True)
    path: Mapped[ioPath] = mapped_column(PathType(length=512))
    status: Mapped[bool] = mapped_column(default=True)

    # relationship
    articles: Mapped[list[WikiArticle]] = relationship(back_populates="topic")

    def __repr__(self) -> str:
        return f"<WikiTopic({self.topic})>"

    @property
    def absolute_path(self) -> ioPath:
        return self.root_dir() / self.path

    @classmethod
    async def create(
            cls,
            session: AsyncSession,
            /,
            name: str,
    ) -> None:
        topic_dir = cls.wiki_dir() / name
        # Create the topic dir
        await topic_dir.mkdir(parents=True, exist_ok=True)
        # Create the topic info
        rel_path = cls.get_rel_path(topic_dir)
        stmt = (
            insert(cls)
            .values({
                "name": name,
                "path": str(rel_path),
            })
        )
        await session.execute(stmt)

    @classmethod
    async def get(
            cls,
            session: AsyncSession,
            /,
            name: str,
    ) -> Self | None:
        stmt = (
            select(cls)
            .where(
                (cls.name == name)
                & (cls.status == True)
            )
        )
        result = await session.execute(stmt)
        return result.scalars().one_or_none()

    @classmethod
    async def get_multiple(
            cls,
            session: AsyncSession,
            /,
            name: str | None = None,
            limit: int = 50,
    ) -> Sequence[Self]:
        stmt = (
            select(cls)
            .where(cls.status == True)
            .limit(limit)
        )
        if name is not None:
            if isinstance(name, list):
                stmt = stmt.where(cls.name.in_(name))
            else:
                stmt = stmt.where(cls.name == name)
        result = await session.execute(stmt)
        return result.scalars().all()

    @classmethod
    async def delete(
            cls,
            session: AsyncSession,
            /,
            name: str,
    ) -> None:
        stmt = (
            update(cls)
            .where(cls.name == name)
            .values({"status": False})
        )
        await session.execute(stmt)

    async def create_template(self, content: str, mode: str = "w") -> None:
        path = self.absolute_path / "template.md"
        async with await path.open(mode) as f:
            await f.write(content)

    async def get_template(self) -> str:
        path = self.absolute_path / "template.md"
        if not await path.exists():
            raise WikiArticleNotFound
        async with await path.open("r") as f:
            content = await f.read()
            return content


class WikiArticle(Base, WikiObject):
    __tablename__ = "wiki_articles"
    __bind_key__ = "app"
    __table_args__ = (
        UniqueConstraint(
            "name", "topic_id",
            name="uq_wiki_articles_name"
        ),
    )
    _lookup_keys = ["topic", "name"]

    id: Mapped[int] = mapped_column(primary_key=True)
    topic_id: Mapped[int] = mapped_column(sa.ForeignKey("wiki_topics.id"))
    name: Mapped[str] = mapped_column(sa.String(length=64))
    version: Mapped[int] = mapped_column(default=1)
    path: Mapped[ioPath] = mapped_column(PathType(length=512))
    status: Mapped[bool] = mapped_column(default=True)

    # relationship
    topic: Mapped[WikiTopic] = relationship(back_populates="articles", lazy="selectin")
    modifications: Mapped[list[WikiArticleModification]] = relationship(back_populates="article")
    images: Mapped[list[WikiArticlePicture]] = relationship(back_populates="article")

    def __repr__(self) -> str:
        return (
            f"<WikiArticle({self.topic}-{self.name}-{self.version}, path={self.path})>"
        )

    @property
    def topic_name(self) -> str:  # Needed for response formatting
        return self.topic.name

    @property
    def absolute_path(self) -> ioPath:
        return self.root_dir() / self.path

    @property
    def content_name(self) -> str:
        return f"content-v{self.version:02d}.md"

    @property
    def content_path(self) -> ioPath:
        return self.path / self.content_name

    @property
    def _abs_content_path(self) -> ioPath:
        return self.absolute_path / self.content_name

    async def set_content(self, content: str) -> None:
        async with await self._abs_content_path.open("w") as f:
            await f.write(content)

    async def get_content(self) -> str:
        async with await self._abs_content_path.open("r") as f:
            content = await f.read()
            return content

    @classmethod
    async def create(
            cls,
            session: AsyncSession,
            /,
            topic: str,
            name: str,
            content: str,
            author_id: int,
    ) -> None:
        topic_obj = await WikiTopic.get(session, name=topic)
        if topic_obj is None:
            raise WikiArticleNotFound
        article_dir = topic_obj.absolute_path / name
        await article_dir.mkdir(parents=True, exist_ok=True)
        rel_path = article_dir.relative_to(current_app.static_dir)
        # Create the article info
        stmt = (
            insert(cls)
            .values({
                "topic_id": topic_obj.id,
                "name": name,
                "path": str(rel_path),
            })
        )
        await session.execute(stmt)
        # Create the article modification
        article = await cls.get_latest_version(session, topic=topic, name=name)
        await WikiArticleModification.create(
            session,
            article=article,
            author_id=author_id,
            modification=ModificationType.creation,
        )
        # Save the article content
        await article.set_content(content)

    @classmethod
    async def get(
            cls,
            session: AsyncSession,
            /,
            topic: str,
            name: str,
            version: int,
    ) -> Self:
        stmt = (
            select(cls)
            .join(WikiTopic, cls.topic_id == WikiTopic.id)
            .where(
                (WikiTopic.name == topic)
                & (cls.name == name)
                & (cls.version == version)
                & (cls.status == True)
            )
        )
        result = await session.execute(stmt)
        return result.scalars().one_or_none()

    @classmethod
    async def get_multiple(
            cls,
            session: AsyncSession,
            /,
            topic: list[str] | str | None = None,
            name: list[str] | str | None = None,
            limit: int = 50,
    ) -> Sequence[Self]:
        stmt = (
            select(cls)
            .join(WikiTopic, cls.topic_id == WikiTopic.id)
            .where(cls.status == True)
            .limit(limit)
        )
        if topic:
            if isinstance(topic, list):
                stmt = stmt.where(WikiTopic.name.in_(topic))
            else:
                stmt = stmt.where(WikiTopic.name == topic)
        if name:
            if isinstance(name, list):
                stmt = stmt.where(cls.name.in_(name))
            else:
                stmt = stmt.where(cls.name == name)
        result = await session.execute(stmt)
        return result.scalars().all()

    @classmethod
    async def get_latest_version(
            cls,
            session: AsyncSession,
            /,
            topic: str,
            name: str
    ) -> Self | None:
        stmt = (
            select(cls)
            .join(WikiTopic, cls.topic_id == WikiTopic.id)
            .where(
                (WikiTopic.name == topic)
                & (cls.name == name)
                & (cls.status == True)
            )
            .order_by(cls.version.desc())
            .limit(1)
        )
        result = await session.execute(stmt)
        return result.scalars().one_or_none()

    @classmethod
    async def get_by_topic(
            cls,
            session: AsyncSession,
            /,
            topic: str,
            limit: int = 50
    ) -> Sequence[Self]:
        stmt = (
            select(cls)
            .join(WikiTopic, cls.topic_id == WikiTopic.id)
            .where(
                (WikiTopic.name == topic)
                & (cls.status == True)
            )
            .limit(limit)
        )
        result = await session.execute(stmt)
        return result.scalars().all()

    @classmethod
    async def get_history(
            cls,
            session: AsyncSession,
            /,
            topic: str,
            name: str,
            limit: int = 50,
    ) -> Sequence[WikiArticleModification]:
        article = await cls.get_latest_version(session, topic=topic, name=name)
        if not article:
            raise ValueError("Article not found")
        history = await WikiArticleModification.get_for_article(
            session, article_id=article.id, limit=limit)
        return history

    @classmethod
    async def update(
            cls,
            session: AsyncSession,
            /,
            topic: str,
            name: str,
            content: str,
            author_id: int,
    ) -> None:
        article = await cls.get_latest_version(session, topic=topic, name=name)
        if not article:
            raise WikiArticleNotFound
        new_version = article.version + 1
        # Update the article info
        stmt = (
            update(cls)
            .where(cls.id == article.id)
            .values({"version": new_version})
        )
        await session.execute(stmt)
        # Create the article modification
        article = await cls.get_latest_version(session, topic=topic, name=name)
        await WikiArticleModification.create(
            session,
            article=article,
            author_id=author_id,
            modification=ModificationType.update,
        )
        # Save the article content
        await article.set_content(content)

    @classmethod
    async def delete(
            cls,
            session: AsyncSession,
            /,
            topic: str,
            name: str,
            author_id: int,
    ) -> None:
        article = await cls.get_latest_version(session, topic=topic, name=name)
        if not article:
            raise WikiArticleNotFound
        # Update the article info
        stmt = (
            update(cls)
            .where(cls.id == article.id)
            .values({"status": False})
        )
        await session.execute(stmt)
        # Create the article modification
        await WikiArticleModification.create(
            session,
            article=article,
            author_id=author_id,
            modification=ModificationType.deletion,
        )


class WikiArticleModification(Base):
    __tablename__ = "wiki_articles_modifications"
    __bind_key__ = "app"
    __table_args__ = (
        UniqueConstraint(
            "article_id", "article_version", "modification_type",
            name="uq_wiki_articles_modifications"
        ),
    )
    _lookup_keys = ["topic", "article", "version"]

    id: Mapped[int] = mapped_column(primary_key=True)
    article_id: Mapped[int] = mapped_column(sa.ForeignKey("wiki_articles.id"))
    article_version: Mapped[int] = mapped_column()
    modification_type: Mapped[ModificationType] = mapped_column()
    timestamp: Mapped[datetime] = mapped_column(UtcDateTime, default=func.current_timestamp())
    author_id: Mapped[str] = mapped_column(sa.ForeignKey("users.id"))

    # relationship
    article: Mapped[WikiArticle] = relationship(back_populates="modifications", lazy="selectin")
    author: Mapped[User] = relationship()

    def __repr__(self) -> str:
        return (
            f"<WikiArticleModification({self.article_id}, "
            f"timestamp={self.timestamp}, modification_type={self.modification_type})>"
        )

    @property
    def topic_name(self) -> str:  # Needed for response formatting
        return self.article.topic.name

    @property
    def article_name(self) -> str:  # Needed for response formatting
        return self.article.name

    @classmethod
    async def create(
            cls,
            session: AsyncSession,
            /,
            article: WikiArticle,
            author_id: int,
            modification: ModificationType,
    ) -> None:
        stmt = (
            insert(cls)
            .values({
                "article_id": article.id,
                "article_version": article.version,
                "modification_type": modification,
                "author_id": author_id,
            })
        )
        await session.execute(stmt)

    @classmethod
    async def get_for_article(
            cls,
            session: AsyncSession,
            /,
            article_id: int,
            limit: int = 50,
    ) -> Sequence[Self]:
        stmt = (
            select(cls)
            .where(cls.article_id == article_id)
            .limit(limit)
        )
        result = await session.execute(stmt)
        return result.scalars().all()

    @classmethod
    async def delete(
            cls,
            session: AsyncSession,
            /,
            article_id: int,
            article_version,
    ) -> None:
        stmt = (
            delete(cls)
            .where(
                (cls.article_id == article_id)
                & (cls.article_version == article_version)
            )
        )
        await session.execute(stmt)


class WikiArticlePicture(Base, WikiObject):
    __tablename__ = "wiki_articles_pictures"
    __bind_key__ = "app"
    __table_args__ = (
        UniqueConstraint(
            "article_id", "name",
            name="uq_wiki_article_id"
        ),
    )
    _lookup_keys = ["topic", "article", "name"]

    id: Mapped[int] = mapped_column(primary_key=True)
    article_id: Mapped[int] = mapped_column(sa.ForeignKey("wiki_articles.id"))
    name: Mapped[str] = mapped_column(sa.String(length=64))
    path: Mapped[ioPath] = mapped_column(PathType(length=512))
    status: Mapped[bool] = mapped_column(default=True)
    timestamp: Mapped[datetime] = mapped_column(UtcDateTime, default=func.current_timestamp())
    author_id: Mapped[str] = mapped_column(sa.ForeignKey("users.id"))

    # relationship
    article: Mapped[WikiArticle] = relationship(back_populates="images", lazy="selectin")

    def __repr__(self) -> str:
        return (
            f"<WikiArticlePicture({self.article_id}, timestamp={self.timestamp})>"
        )

    @property
    def absolute_path(self) -> ioPath:
        return self.root_dir() / self.path

    @property
    def topic_name(self) -> str:
        return self.article.topic.name

    @property
    def article_name(self) -> str:
        return self.article.name

    async def set_image(self, image: bytes) -> None:
        async with await self.absolute_path.open("wb") as f:
            await f.write(image)

    async def get_image(self) -> bytes:
        async with await self.absolute_path.open("rb") as f:
            image = await f.read()
            return image

    @classmethod
    async def create(
            cls,
            session: AsyncSession,
            /,
            topic: str,
            article: str,
            name: str,
            content: bytes,
            author_id: int,
    ) -> None:
        article_obj = await WikiArticle.get_latest_version(
            session, topic=topic, name=article)
        if article_obj is None:
            raise WikiArticleNotFound
        picture_path = article_obj.absolute_path / name
        rel_path = cls.get_rel_path(picture_path)
        # Create the picture info
        stmt = (
            insert(cls)
            .values({
                "article_id": article_obj.id,
                "name": name,
                "path": str(rel_path),
                "author_id": author_id,
            })
        )
        await session.execute(stmt)
        # Save the picture content
        picture_info = await cls.get(
            session, topic=topic, article=article, name=name)
        await picture_info.set_image(content)

    @classmethod
    async def get(
            cls,
            session: AsyncSession,
            /,
            topic: str,
            article: str,
            name: str,
    ) -> Self | None:
        article_obj = await WikiArticle.get_latest_version(
            session, topic=topic, name=article)
        if article_obj is None:
            raise WikiArticleNotFound
        stmt = (
            select(cls)
            .where(
                (cls.article_id == article_obj.id)
                & (cls.name == name)
                & (cls.status == True)
            )
        )
        result = await session.execute(stmt)
        return result.scalars().one_or_none()

    @classmethod
    async def delete(
            cls,
            session: AsyncSession,
            /,
            topic: str,
            article: str,
            name: str,
    ) -> None:
        article_obj = await WikiArticle.get_latest_version(
            session, topic=topic, name=article)
        if article_obj is None:
            raise WikiArticleNotFound
        # Mark the picture as inactive
        stmt = (
            update(cls)
            .where(
                (cls.article_id == article_obj.id)
                & (cls.name == name)
            )
            .values({"status": False})
        )
        await session.execute(stmt)
        # Rename the picture content
        #picture_info = await cls.get(session, article_obj=article_obj, name=name)
        #new_picture_path = article_obj.absolute_path / f"DELETED-{name}.jpeg"
        #await picture_info.absolute_path.rename(new_picture_path)
