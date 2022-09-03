from datetime import datetime, timezone
from hashlib import md5
import time as ctime

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
import sqlalchemy as sa
from sqlalchemy import orm, select
from sqlalchemy.ext.asyncio import AsyncSession

from ._base import ArchiveLink, base
from .common import BaseWarning
from src.app.utils import app_config
from src.core.utils import ExpiredTokenError, InvalidTokenError, Tokenizer


argon2_hasher = PasswordHasher()


# ---------------------------------------------------------------------------
#   Users-related models, located in db_users
# ---------------------------------------------------------------------------
class Permission:
    VIEW = 1
    EDIT = 2
    OPERATE = 4
    ADMIN = 8


class Role(base):
    __tablename__ = "roles"
    __bind_key__ = "app"
    id = sa.Column(sa.Integer, primary_key=True)
    name = sa.Column(sa.String(64), unique=True)
    default = sa.Column(sa.Boolean, default=False, index=True)
    permissions = sa.Column(sa.Integer)

    # relationship
    users = orm.relationship("User", back_populates="role", lazy="dynamic")

    def __init__(self, **kwargs):
        super(Role, self).__init__(**kwargs)
        if self.permissions is None:
            self.permissions = 0

    @staticmethod
    async def insert_roles(session: AsyncSession):
        roles = {
            "User": [Permission.VIEW, Permission.EDIT],
            "Operator": [Permission.VIEW, Permission.EDIT,
                         Permission.OPERATE],
            "Administrator": [Permission.VIEW, Permission.EDIT,
                              Permission.OPERATE, Permission.ADMIN],
        }
        default_role = "User"
        stmt = select(Role)
        result = await session.execute(stmt)
        roles_in_db = result.scalars().all()
        for r in roles:
            role = None
            for role_in_db in roles_in_db:
                if role_in_db.name == r:
                    role = role_in_db
                    break
            if role is None:
                role = Role(name=r)
            role.reset_permissions()
            for perm in roles[r]:
                role.add_permission(perm)
            role.default = (role.name == default_role)
            session.add(role)
        await session.commit()

    def has_permission(self, perm):
        return self.permissions & perm == perm

    def add_permission(self, perm):
        if not self.has_permission(perm):
            self.permissions += perm

    def remove_permission(self, perm):
        if self.has_permission(perm):
            self.permissions -= perm

    def reset_permissions(self):
        self.permissions = 0

    def __repr__(self):
        return f"<Role {self.name}>"


# TODO: move elsewhere
class UserMixin:
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

    def can(self, perm) -> bool:
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


class User(base, UserMixin):
    __tablename__ = "users"
    __bind_key__ = "app"
    id = sa.Column(sa.Integer, primary_key=True)
    username = sa.Column(sa.String(64), index=True, unique=True)
    email = sa.Column(sa.String(120), index=True, unique=True)

    # User authentication fields
    password_hash = sa.Column(sa.String(128))
    confirmed = sa.Column(sa.Boolean, default=False)
    role_id = sa.Column(sa.Integer, sa.ForeignKey("roles.id"))

    # User registration fields
    token = sa.Column(sa.String(32))
    registration_datetime = sa.Column(sa.DateTime, default=datetime.now(timezone.utc))

    # User information fields
    firstname = sa.Column(sa.String(64))
    lastname = sa.Column(sa.String(64))
    last_seen = sa.Column(sa.DateTime, default=datetime.now(timezone.utc))

    # User notifications / services fields
    daily_recap = sa.Column(sa.Boolean, default=False)
    daily_recap_channel_id = sa.Column(
        sa.Integer, sa.ForeignKey("communication_channels.id"))
    telegram = sa.Column(sa.Boolean, default=False)
    telegram_chat_id = sa.Column(sa.String(16), unique=True)

    # relationship
    role = orm.relationship("Role", back_populates="users", lazy="joined")
    daily_recap_channel = orm.relationship("CommunicationChannel",
                                           back_populates="users")
    calendar = orm.relationship("CalendarEvent", back_populates="user")

    @classmethod
    async def create(cls, session: AsyncSession, **kwargs):
        user = User(**kwargs)
        if user.role is None:
            if user.email in app_config.get("OURANOS_ADMIN", ()):
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
            gaia = User(username="Ouranos", confirmed=True, role=admin)
            session.add(gaia)
            await session.commit()

    def set_password(self, password):
        self.password_hash = argon2_hasher.hash(password)

    def check_password(self, password):
        try:
            return argon2_hasher.verify(self.password_hash, password)
        except VerificationError:
            return False

    def can(self, perm):
        return self.role is not None and self.role.has_permission(perm)

    def avatar(self, size):
        digest = md5(self.email.lower().encode("utf-8")).hexdigest()
        return f"https://www.gravatar.com/avatar/{digest}?d=identicon&s={size}"

    def create_token(
            self,
            payload: dict,
            secret_key: str = None,
            expires_in: int = 1800,
            **kwargs
    ) -> str:
        _payload = {"user_id": self.id}
        _payload.update(payload)
        if expires_in:
            _payload.update({"exp": ctime.time() + expires_in})
        if kwargs:
            _payload.update(**kwargs)
        return Tokenizer.dumps(_payload, secret_key)

    @staticmethod
    def load_from_token(token: str, token_use: str):
        try:
            payload = Tokenizer.loads(token, app_config["SECRET_KEY"])
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
                "daily_recap_channel_id": self.daily_recap_channel_id,
                "telegram": self.telegram,
                "telegram_chat_id": self.telegram_chat_id,
            })
        return rv


class Service(base):
    __tablename__ = "services"
    __bind_key__ = "app"
    id = sa.Column(sa.Integer, primary_key=True)
    name = sa.Column(sa.String(length=16))
    level = sa.Column(sa.String(length=4))
    status = sa.Column(sa.Boolean, default=False)

    def to_dict(self):
        return {
            "name": self.name,
            "level": self.level,
            "status": self.status,
        }


class CommunicationChannel(base):
    __tablename__ = "communication_channels"
    __bind_key__ = "app"
    id = sa.Column(sa.Integer, primary_key=True)
    name = sa.Column(sa.String(length=16))
    status = sa.Column(sa.Boolean, default=False)

    # relationship
    users = orm.relationship("User", back_populates="daily_recap_channel",
                             lazy="dynamic")

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
    __archive_link__ = ArchiveLink("warnings", "recent")


class CalendarEvent(base):  # TODO: apply similar to warnings
    __tablename__ = "calendar_events"
    __bind_key__ = "app"
    id = sa.Column(sa.Integer, primary_key=True)
    user_id = sa.Column(sa.Integer, sa.ForeignKey("users.id"))
    start_time = sa.Column(sa.DateTime, nullable=False)
    end_time = sa.Column(sa.DateTime, nullable=False)
    type = sa.Column(sa.Integer)
    title = sa.Column(sa.String(length=256))
    description = sa.Column(sa.String(length=2048))
    created_at = sa.Column(sa.DateTime, nullable=False)
    updated_at = sa.Column(sa.DateTime, nullable=False)
    active = sa.Column(sa.Boolean, default=True)
    URL = sa.Column(sa.String(length=1024))
    content = sa.Column(sa.String)

    # relationship
    user = orm.relationship("User", back_populates="calendar")


class GaiaJob(base):
    __tablename__ = "gaia_jobs"
    id = sa.Column(sa.Integer, primary_key=True)
    command = sa.Column(sa.String)
    arguments = sa.Column(sa.String)
    done = sa.Column(sa.Boolean)
