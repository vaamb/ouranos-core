from datetime import datetime, time, timedelta, timezone
from hashlib import md5

import sqlalchemy as sa
from flask import current_app
from flask_login import AnonymousUserMixin, UserMixin
from sqlalchemy import orm
from sqlalchemy.ext.declarative import declared_attr
from werkzeug.security import check_password_hash, generate_password_hash

from app import db, login_manager


def old_data_limit() -> datetime:
    now_utc = datetime.now(timezone.utc)
    return (now_utc - timedelta(days=45)).replace(tzinfo=None)


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
    __bind_key__ = "users"
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

    def add_permission(self, perm):
        if not self.has_permission(perm):
            self.permissions += perm

    def remove_permission(self, perm):
        if self.has_permission(perm):
            self.permissions -= perm

    def reset_permissions(self):
        self.permissions = 0

    def has_permission(self, perm):
        return self.permissions & perm == perm

    def __repr__(self):
        return "<Role {}>".fdbat(self.name)


class User(UserMixin, db.Model):
    __tablename__ = "users"
    __bind_key__ = "users"
    id = sa.Column(sa.Integer, primary_key=True)
    username = sa.Column(sa.String(64), index=True, unique=True)
    email = sa.Column(sa.String(120), index=True, unique=True)
    password_hash = sa.Column(sa.String(128))
    role_id = sa.Column(sa.Integer, sa.ForeignKey("roles.id"))
    confirmed = sa.Column(sa.Boolean, default=False)
    firstname = sa.Column(sa.String(64), unique=True)
    lastname = sa.Column(sa.String(64), unique=True)
    last_seen = sa.Column(sa.DateTime, default=datetime.utcnow)
    notifications = sa.Column(sa.Boolean, default=False)
    telegram_chat_id = sa.Column(sa.String(16), unique=True)

    # relationship
    role = orm.relationship("Role", back_populates="users")

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


# ---------------------------------------------------------------------------
#   Base models common to main app and archive
# ---------------------------------------------------------------------------
# TODO: replace datetime by time_stamp
class baseData(db.Model):
    __abstract__ = True
    row_id = sa.Column(sa.Integer, primary_key=True)
    measure = sa.Column(sa.Integer, index=True)
    datetime = sa.Column(sa.DateTime, index=True)
    value = sa.Column(sa.Float(precision=2))

    @declared_attr
    def ecosystem_id(cls):
        return sa.Column(sa.String(length=8), sa.ForeignKey("ecosystems.id"),
                         index=True)

    @declared_attr
    def sensor_id(cls):
        return sa.Column(sa.String(length=16), sa.ForeignKey("hardware.id"),
                         index=True)


class baseHealth(db.Model):
    __abstract__ = True
    row_id = sa.Column(sa.Integer, primary_key=True)
    datetime = sa.Column(sa.DateTime, nullable=False)
    green = sa.Column(sa.Integer)
    necrosis = sa.Column(sa.Integer)
    health_index = sa.Column(sa.Float(precision=1))

    @declared_attr
    def ecosystem_id(cls):
        return sa.Column(sa.String(length=8), sa.ForeignKey("ecosystems.id"),
                         index=True)


# ---------------------------------------------------------------------------
#   Main app-related models, located in db_main and db_archive
# ---------------------------------------------------------------------------
class engineManager(db.Model):
    __tablename__ = "engine_managers"
    uid = sa.Column(sa.String(length=16), primary_key=True)
    sid = sa.Column(sa.String(length=32))

    # relationship
    ecosystem = orm.relationship("Ecosystem", back_populates="manager", lazy="dynamic")


class Ecosystem(db.Model):
    __tablename__ = "ecosystems"
    id = sa.Column(sa.String(length=8), primary_key=True)
    name = sa.Column(sa.String(length=32))
    status = sa.Column(sa.Boolean, default=False)
    last_seen = sa.Column(sa.DateTime)

    lighting = sa.Column(sa.Boolean, default=False)
    watering = sa.Column(sa.Boolean, default=False)
    climate = sa.Column(sa.Boolean, default=False)
    health = sa.Column(sa.Boolean, default=False)
    alarms = sa.Column(sa.Boolean, default=False)

    webcam = sa.Column(sa.String(length=8))

    day_start = sa.Column(sa.Time, default=time(8, 00))
    day_temperature = sa.Column(sa.Float(precision=1), default=22.0)
    day_humidity = sa.Column(sa.Integer, default=70.0)
    day_light = sa.Column(sa.Integer, default=0.0)

    night_start = sa.Column(sa.Time, default=time(20, 00))
    night_temperature = sa.Column(sa.Float(precision=1), default=17.0)
    night_humidity = sa.Column(sa.Integer, default=40.0)
    night_light = sa.Column(sa.Integer, default=0.0)

    temperature_hysteresis = sa.Column(sa.Float(precision=1), default=1.0)
    humidity_hysteresis = sa.Column(sa.Integer, default=1.0)
    light_hysteresis = sa.Column(sa.Integer, default=0.0)

    manager_uid = sa.Column(sa.Integer, sa.ForeignKey("engine_managers.uid"))

    # relationship
    manager = orm.relationship("engineManager", back_populates="ecosystem")
    hardware = orm.relationship("Hardware", back_populates="ecosystem", lazy="dynamic")
    # plants = orm.relationship("Plant", back_populates="ecosystem")
    data = orm.relationship("sensorData", back_populates="ecosystem", lazy="dynamic")
    health_data = orm.relationship("Health", back_populates="ecosystem", lazy="dynamic")
    light = orm.relationship("Light", back_populates="ecosystem", lazy="dynamic")
    warnings = orm.relationship("Warning", back_populates="ecosystem")


class Hardware(db.Model):
    __tablename__ = "hardware"
    id = sa.Column(sa.String(length=32), primary_key=True)
    ecosystem_id = sa.Column(sa.String(length=8), sa.ForeignKey("ecosystems.id"))
    name = sa.Column(sa.String(length=32))
    level = sa.Column(sa.String(length=16))
    pin = sa.Column(sa.Integer)
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
    __tablename__ = "sensor_data"

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

class System(db.Model):
    __tablename__ = "system"
    row_id = sa.Column(sa.Integer, primary_key=True)
    datetime = sa.Column(sa.DateTime, nullable=False)
    CPU_used = sa.Column(sa.Float(precision=1))
    CPU_temp = sa.Column(sa.Float(precision=1))
    RAM_total = sa.Column(sa.Float(precision=2))
    RAM_used = sa.Column(sa.Float(precision=2))
    DISK_total = sa.Column(sa.Float(precision=2))
    DISK_used = sa.Column(sa.Float(precision=2))


class Service(db.Model):
    __tablename__ = "services"
    name = sa.Column(sa.String(length=16), primary_key=True)
    status = sa.Column(sa.Boolean, default=False)

    @staticmethod
    def insert_services():
        services = ["telegram"]
        for s in services:
            service = Service.query.filter_by(name=s).first()
            if service is None:
                service = Service(name=s)
            db.session.add(service)
        db.session.commit()


class Warning(db.Model):
    __tablename__ = "warnings"
    row_id = sa.Column(sa.Integer, primary_key=True)
    datetime = sa.Column(sa.DateTime, nullable=False)
    level = sa.Column(sa.Integer)
    message = sa.Column(sa.String)
    seen = sa.Column(sa.Boolean)
    solved = sa.Column(sa.Boolean)
    ecosystem_id = sa.Column(sa.String(length=8), sa.ForeignKey("ecosystems.id"))

    # relationship
    ecosystem = orm.relationship("Ecosystem", back_populates="warnings")


# ---------------------------------------------------------------------------
#   Models used for archiving, located in db_archive
# ---------------------------------------------------------------------------
class archiveData(baseData):
    __tablename__ = "data_archive"
    __bind_key__ = "archive"


class archiveHealth(baseHealth):
    __tablename__ = "health_archive"
    __bind_key__ = "archive"
