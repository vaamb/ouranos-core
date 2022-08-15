from datetime import datetime, timezone
from hashlib import md5
import time as ctime

#from flask import current_app
#from flask_login import UserMixin
import sqlalchemy as sa
from sqlalchemy import orm
from werkzeug.security import check_password_hash, generate_password_hash

from . import archive_link, base
from . common import BaseAppWarning
from src.utils import ExpiredTokenError, InvalidTokenError, Tokenizer


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
    def insert_roles(db):
        roles = {
            "User": [Permission.VIEW, Permission.EDIT],
            "Operator": [Permission.VIEW, Permission.EDIT,
                         Permission.OPERATE],
            "Administrator": [Permission.VIEW, Permission.EDIT,
                              Permission.OPERATE, Permission.ADMIN],
        }
        default_role = "User"
        for r in roles:
            role = Role.query.filter_by(name=r).first()
            if role is None:
                role = Role(name=r)
            role.reset_permissions()
            for perm in roles[r]:
                role.add_permission(perm)
            role.default = (role.name == default_role)
            db.session.add(role)
        db.session.commit()

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


class User(base):  # add UserMixin
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
    registration_datetime = sa.Column(sa.DateTime)

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
    role = orm.relationship("Role", back_populates="users")
    daily_recap_channel = orm.relationship("CommunicationChannel",
                                           back_populates="users")
    calendar = orm.relationship("CalendarEvent", back_populates="user")

    def __init__(self, **kwargs):
        super(User, self).__init__(**kwargs)
        if self.role is None:
            if self.email in current_app.config["OURANOS_ADMIN"]:
                self.role = Role.query.filter_by(name="Administrator").first()
            else:
                self.role = Role.query.filter_by(default=True).first()

    @staticmethod
    def insert_gaia(db):
        gaia = db.session.query(User).filter_by(username="Ouranos").first()
        if not gaia:
            admin = db.session.query(Role).filter_by(
                name="Administrator").first()
            gaia = User(username="Ouranos", confirmed=True, role=admin)
            db.session.add(gaia)
            db.session.commit()

    def set_password(self, password):
        self.password_hash = generate_password_hash(
            password, method="pbkdf2:sha256:200000"
        )

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def can(self, perm):
        return self.role is not None and self.role.has_permission(perm)

    def avatar(self, size):
        digest = md5(self.email.lower().encode("utf-8")).hexdigest()
        return f"https://www.gravatar.com/avatar/{digest}?d=identicon&s={size}"

    def create_token(
            self,
            use: str,
            secret_key=None,
            expires_in: int = 1800,
            **kwargs
    ) -> str:
        if not secret_key:
            secret_key = current_app.config["SECRET_KEY"]
        payload = {"user_id": self.id, "use": use}
        if expires_in:
            payload.update({"exp": ctime.time() + expires_in})
        if kwargs:
            payload.update(**kwargs)
        return Tokenizer.dumps(secret_key, payload)

    @staticmethod
    def load_from_token(token: str, token_use: str):
        try:
            payload = Tokenizer.loads(current_app.config["SECRET_KEY"], token)
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
    def insert_channels(db):
        channels = ["telegram"]
        for c in channels:
            channel = CommunicationChannel.query.filter_by(name=c).first()
            if channel is None:
                channel = CommunicationChannel(name=c)
            db.session.add(channel)
        db.session.commit()


# TODO: When problems solved, after x days: goes to archive
class AppWarning(BaseAppWarning):
    __tablename__ = "warnings"
    __archive_link__ = archive_link("warnings", "recent")


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
