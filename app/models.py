from datetime import datetime, time, timedelta, timezone
from hashlib import md5

import sqlalchemy as sa
from flask import current_app
from flask_login import AnonymousUserMixin, UserMixin
from sqlalchemy import orm
from sqlalchemy.ext.declarative import declared_attr
from werkzeug.security import check_password_hash, generate_password_hash

from app import db, login_manager


# TODO: add an archive function in models which can be archived and add a task to apscheduler every monday at 1 which archive old data
def old_data_limit() -> datetime:
    now_utc = datetime.now(timezone.utc)
    return (now_utc - timedelta(days=60)).replace(tzinfo=None)


# ---------------------------------------------------------------------------
#   Users-related models, located in db_users
# ---------------------------------------------------------------------------
class Permission:
    VIEW = 1
    EDIT = 2
    OPERATE = 4
    ADMIN = 8


class Role(db.Model):
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
    def insert_roles():
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


class User(UserMixin, db.Model):
    __tablename__ = "users"
    __bind_key__ = "app"
    id = sa.Column(sa.Integer, primary_key=True)
    username = sa.Column(sa.String(64), index=True, unique=True)
    email = sa.Column(sa.String(120), index=True, unique=True)
    password_hash = sa.Column(sa.String(128))
    role_id = sa.Column(sa.Integer, sa.ForeignKey("roles.id"))
    confirmed = sa.Column(sa.Boolean, default=False)
    firstname = sa.Column(sa.String(64))
    lastname = sa.Column(sa.String(64))
    last_seen = sa.Column(sa.DateTime, default=datetime.utcnow)

    # notifications / services
    daily_recap = sa.Column(sa.Boolean, default=False)
    daily_recap_channel_id = sa.Column(sa.Integer,
                                       sa.ForeignKey("communication_channels.id"))
    telegram = sa.Column(sa.Boolean, default=False)
    telegram_chat_id = sa.Column(sa.String(16), unique=True)

    # relationship
    role = orm.relationship("Role", back_populates="users")
    daily_recap_channel = orm.relationship("comChannel", back_populates="users")

    def __init__(self, **kwargs):
        super(User, self).__init__(**kwargs)
        if self.role is None:
            if self.email in current_app.config["GAIA_ADMIN"]:
                self.role = Role.query.filter_by(name="Administrator").first()
            else:
                self.role = Role.query.filter_by(default=True).first()

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def can(self, perm):
        return self.role is not None and self.role.has_permission(perm)

    # properties for easy jinja2 templates
    @property
    def is_operator(self):
        return self.can(Permission.OPERATE)

    @property
    def is_administrator(self):
        return self.can(Permission.ADMIN)

    def avatar(self, size):
        digest = md5(self.email.lower().encode("utf-8")).hexdigest()
        return "https://www.gravatar.com/avatar/{}?d=identicon&s={}".fdbat(
            digest, size)


class AnonymousUser(AnonymousUserMixin):
    def can(self):
        return False

    # properties for easy jinja2 templates
    @property
    def is_operator(self):
        return False

    @property
    def is_administrator(self):
        return False


login_manager.anonymous_user = AnonymousUser
login_manager.login_view = 'auth.login'


@login_manager.user_loader
def load_user(id):
    return User.query.get(int(id))


class Service(db.Model):
    __tablename__ = "services"
    __bind_key__ = "app"
    id = sa.Column(sa.Integer, primary_key=True)
    name = sa.Column(sa.String(length=16))
    level = sa.Column(sa.String(length=4))
    status = sa.Column(sa.Boolean, default=False)


class comChannel(db.Model):
    __tablename__ = "communication_channels"
    __bind_key__ = "app"
    id = sa.Column(sa.Integer, primary_key=True)
    name = sa.Column(sa.String(length=16))
    status = sa.Column(sa.Boolean, default=False)

    # relationship
    users = orm.relationship("User", back_populates="daily_recap_channel",
                             lazy="dynamic")

    @staticmethod
    def insert_channels():
        channels = ["telegram"]
        for c in channels:
            channel = comChannel.query.filter_by(name=c).first()
            if channel is None:
                channel = comChannel(name=c)
            db.session.add(channel)
        db.session.commit()


# ---------------------------------------------------------------------------
#   Base models common to main app and archive
# ---------------------------------------------------------------------------
# TODO: replace datetime by time_stamp
class baseData(db.Model):
    __abstract__ = True
    measure = sa.Column(sa.Integer, primary_key=True)
    datetime = sa.Column(sa.DateTime, primary_key=True)
    value = sa.Column(sa.Float(precision=2))

    @declared_attr
    def ecosystem_id(cls):
        return sa.Column(sa.String(length=8), sa.ForeignKey("ecosystems.id"),
                         primary_key=True)

    @declared_attr
    def sensor_id(cls):
        return sa.Column(sa.String(length=16), sa.ForeignKey("hardware.id"),
                         primary_key=True)


class baseHealth(db.Model):
    __abstract__ = True
    datetime = sa.Column(sa.DateTime, nullable=False, primary_key=True)
    green = sa.Column(sa.Integer)
    necrosis = sa.Column(sa.Integer)
    health_index = sa.Column(sa.Float(precision=1))

    @declared_attr
    def ecosystem_id(cls):
        return sa.Column(sa.String(length=8), sa.ForeignKey("ecosystems.id"),
                         index=True, primary_key=True)


class baseWarning(db.Model):
    __abstract__ = True
    row_id = sa.Column(sa.Integer, primary_key=True)
    datetime = sa.Column(sa.DateTime, nullable=False)
    level = sa.Column(sa.Integer)
    message = sa.Column(sa.String)
    seen = sa.Column(sa.Boolean)
    solved = sa.Column(sa.Boolean)

    @declared_attr
    def ecosystem_id(cls):
        return sa.Column(sa.String(length=8), sa.ForeignKey("ecosystems.id"),
                         index=True)


class baseSystem(db.Model):
    __abstract__ = True
    datetime = sa.Column(sa.DateTime, nullable=False, primary_key=True)
    CPU_used = sa.Column(sa.Float(precision=1))
    CPU_temp = sa.Column(sa.Float(precision=1))
    RAM_total = sa.Column(sa.Float(precision=2))
    RAM_used = sa.Column(sa.Float(precision=2))
    DISK_total = sa.Column(sa.Float(precision=2))
    DISK_used = sa.Column(sa.Float(precision=2))


# ---------------------------------------------------------------------------
#   Main app-related models, located in db_main and db_archive
# ---------------------------------------------------------------------------
class engineManager(db.Model):
    __tablename__ = "engine_managers"
    uid = sa.Column(sa.String(length=16), primary_key=True)
    sid = sa.Column(sa.String(length=32))
    last_seen = sa.Column(sa.DateTime)
    address = sa.Column(sa.String(length=24))

    # relationship
    ecosystem = orm.relationship("Ecosystem", back_populates="manager", lazy="dynamic")


Management = {
    "sensors": 1,
    "light": 2,
    "climate": 4,
    "watering": 8,
    "health": 16,
    "alarms": 32,
    "webcam": 64,
}


class Ecosystem(db.Model):
    __tablename__ = "ecosystems"
    id = sa.Column(sa.String(length=8), primary_key=True)
    name = sa.Column(sa.String(length=32))
    status = sa.Column(sa.Boolean, default=False)
    last_seen = sa.Column(sa.DateTime)
    management = sa.Column(sa.Integer)
    day_start = sa.Column(sa.Time, default=time(8, 00))
    night_start = sa.Column(sa.Time, default=time(20, 00))
    manager_uid = sa.Column(sa.Integer, sa.ForeignKey("engine_managers.uid"))

    # relationship
    manager = orm.relationship("engineManager", back_populates="ecosystem")
    environment_parameters = orm.relationship("environmentParameter", back_populates="ecosystem")
    hardware = orm.relationship("Hardware", back_populates="ecosystem", lazy="dynamic")
    # plants = orm.relationship("Plant", back_populates="ecosystem")
    data = orm.relationship("sensorData", back_populates="ecosystem", lazy="dynamic")
    health_data = orm.relationship("Health", back_populates="ecosystem", lazy="dynamic")
    light = orm.relationship("Light", back_populates="ecosystem", lazy="dynamic")
    warnings = orm.relationship("Warning", back_populates="ecosystem")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if self.management is None:
            self.management = 0

    def manages(self, mng):
        return self.management & mng == mng

    def add_management(self, mng):
        if not self.manages(mng):
            self.management += mng

    def remove_management(self, mng):
        if self.manages(mng):
            self.management -= mng

    def reset_managements(self):
        self.management = 0


class environmentParameter(db.Model):
    __tablename__ = "environment_parameters"
    ecosystem_id = sa.Column(sa.String(length=8), sa.ForeignKey("ecosystems.id"),
                             primary_key=True)
    parameter = sa.Column(sa.String(length=16), primary_key=True)
    moment_of_day = sa.Column(sa.String(length=8), primary_key=True)
    value = sa.Column(sa.Float(precision=2))
    hysteresis = sa.Column(sa.Float(precision=2))

    # relationship
    ecosystem = orm.relationship("Ecosystem", back_populates="environment_parameters")


class Hardware(db.Model):
    __tablename__ = "hardware"
    id = sa.Column(sa.String(length=32), primary_key=True)
    ecosystem_id = sa.Column(sa.String(length=8), sa.ForeignKey("ecosystems.id"))
    name = sa.Column(sa.String(length=32))
    level = sa.Column(sa.String(length=16))
    address = sa.Column(sa.String(length=16))
    type = sa.Column(sa.String(length=16))
    model = sa.Column(sa.String(length=32))
    last_log = sa.Column(sa.DateTime)
    # plant_id = sa.Column(sa.String(8), sa.ForeignKey("plants.id"))

    # relationship
    ecosystem = orm.relationship("Ecosystem", back_populates="hardware")
    # plants = orm.relationship("Plant", back_populates="sensors")
    data = orm.relationship("sensorData", back_populates="sensor", lazy="dynamic")


sa.Index("idx_sensors_type", Hardware.type, Hardware.level)


"""
class Plant(db.Model):
    __tablename__ = "plants"
    id = sa.Column(sa.String(16), primary_key=True)
    name = sa.Column(sa.String(32))
    ecosystem_id = sa.Column(sa.String(8), sa.ForeignKey("ecosystems.id"))
    species = sa.Column(sa.String(32), index=True, nullable=False)
    sowing_date = sa.Column(sa.DateTime)
    #relationship
    ecosystem = orm.relationship("Ecosystem", back_populates="plants")
    sensors = orm.relationship("Hardware", back_populates="plants")
"""


class sensorData(baseData):
    __tablename__ = "sensors_data"

    # relationships
    ecosystem = orm.relationship("Ecosystem", back_populates="data")
    sensor = orm.relationship("Hardware", back_populates="data")

    @staticmethod
    def archive():
        pass
        # TODO


class Light(db.Model):
    __tablename__ = "light"
    ecosystem_id = sa.Column(sa.String(length=8), sa.ForeignKey("ecosystems.id"), primary_key=True)
    status = sa.Column(sa.Boolean)
    expected_status = sa.Column(sa.Boolean)
    mode = sa.Column(sa.String(length=12))
    method = sa.Column(sa.String(length=12))
    morning_start = sa.Column(sa.Time)
    morning_end = sa.Column(sa.Time)
    evening_start = sa.Column(sa.Time)
    evening_end = sa.Column(sa.Time)

    # relationships
    ecosystem = orm.relationship("Ecosystem", back_populates="light")


class Health(baseHealth):
    __tablename__ = "health"

    # relationships
    ecosystem = orm.relationship("Ecosystem", back_populates="health_data")


# TODO: When problems solved, after x days: goes to archive
class Warning(baseWarning):
    __tablename__ = "warnings"

    # relationship
    ecosystem = orm.relationship("Ecosystem", back_populates="warnings")


class System(baseSystem):
    __tablename__ = "system"


# ---------------------------------------------------------------------------
#   Models used for archiving, located in db_archive
# ---------------------------------------------------------------------------
class archiveData(baseData):
    __tablename__ = "data_archive"
    __bind_key__ = "archive"

    ecosystem_id = sa.Column(sa.String(length=8), primary_key=True)
    sensor_id = sa.Column(sa.String(length=16), primary_key=True)


class archiveHealth(baseHealth):
    __tablename__ = "health_archive"
    __bind_key__ = "archive"

    ecosystem_id = sa.Column(sa.String(length=8), primary_key=True)


class archiveWarning(baseWarning):
    __tablename__ = "warnings_archive"
    __bind_key__ = "archive"

    ecosystem_id = sa.Column(sa.String(length=8), primary_key=True)


class archiveSystem(baseSystem):
    __tablename__ = "system_archive"
    __bind_key__ = "archive"
