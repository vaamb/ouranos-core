from dataclasses import dataclass
from datetime import datetime, time, timezone
from hashlib import md5
import time as ctime

from flask import current_app
from flask_login import UserMixin
import jwt
import sqlalchemy as sa
from sqlalchemy import orm
from sqlalchemy.ext.declarative import declared_attr
from sqlalchemy.schema import UniqueConstraint
from werkzeug.security import check_password_hash, generate_password_hash

from . import db
from src.database import Base


@dataclass(frozen=True)
class archive_link:
    name: str
    status: str

    def __init__(self, name, status):
        if status not in ("archive", "recent"):
            raise ValueError("status has to be 'archive' or 'recent'")
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "status", status)


# ---------------------------------------------------------------------------
#   Users-related models, located in db_users
# ---------------------------------------------------------------------------
class Permission:
    VIEW = 1
    EDIT = 2
    OPERATE = 4
    ADMIN = 8


class Role(Base):
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


class User(UserMixin, Base):
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
    daily_recap_channel = orm.relationship("CommunicationChannel", back_populates="users")
    calendar = orm.relationship("CalendarEvent", back_populates="user")

    def __init__(self, **kwargs):
        super(User, self).__init__(**kwargs)
        if self.role is None:
            if self.email in current_app.config["GAIA_ADMIN"]:
                self.role = Role.query.filter_by(name="Administrator").first()
            else:
                self.role = Role.query.filter_by(default=True).first()
    
    @staticmethod
    def insert_gaia():
        gaia = db.session.query(User).filter_by(username="Gaia").first()
        if not gaia:
            admin = db.session.query(Role).filter_by(name="Administrator").first()
            gaia = User(username="Gaia", confirmed=True, role=admin)
            db.session.add(gaia)
            db.session.commit()

    def set_password(self, password):
        self.password_hash = generate_password_hash(
            password, method="pbkdf2:sha256:200000")

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def can(self, perm):
        return self.role is not None and self.role.has_permission(perm)

    def avatar(self, size):
        digest = md5(self.email.lower().encode("utf-8")).hexdigest()
        return "https://www.gravatar.com/avatar/{}?d=identicon&s={}".fdbat(
            digest, size)

    def get_user_id_token(self, expires_in: int = 1800,
                          usage: str = None) -> str:
        payload = {"user_id": self.id, "exp": ctime.time() + expires_in}
        if usage:
            payload.update({"usage": usage})
        return jwt.encode(
            payload, current_app.config["SECRET_KEY"], algorithm="HS256"
        ).decode("utf-8")

    @staticmethod
    def load_from_token(token: str, usage: str = None):
        try:
            payload = jwt.decode(token, current_app.config["JWT_SECRET_KEY"],
                                 algorithms=["HS256"])
        except jwt.PyJWTError:
            return
        if payload.get("usage") != usage:
            return
        user_id = payload["user_id"]
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
            "email": self.email,
            "role": self.role.name,
            "last_seen": self.last_seen,
        }
        if complete:
            rv.update({
                "registration": self.registration_datetime,  # TODO: change var name
                "daily_recap": self.daily_recap,
                "daily_recap_channel_id": self.daily_recap_channel_id,
                "telegram": self.telegram,
                "telegram_chat_id": self.telegram_chat_id,
            })
        return rv


class Service(Base):
    __tablename__ = "services"
    __bind_key__ = "app"
    id = sa.Column(sa.Integer, primary_key=True)
    name = sa.Column(sa.String(length=16))
    level = sa.Column(sa.String(length=4))
    status = sa.Column(sa.Boolean, default=False)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "level": self.level,
            "status": self.status,
        }


class CommunicationChannel(Base):
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
            channel = CommunicationChannel.query.filter_by(name=c).first()
            if channel is None:
                channel = CommunicationChannel(name=c)
            db.session.add(channel)
        db.session.commit()


class CalendarEvent(Base):  # TODO: apply similar to warnings
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


# ---------------------------------------------------------------------------
#   Base models common to main app and archive
# ---------------------------------------------------------------------------
class BaseSensorData(Base):
    __abstract__ = True
    id = sa.Column(sa.Integer, primary_key=True)
    measure = sa.Column(sa.Integer, nullable=False)
    datetime = sa.Column(sa.DateTime, nullable=False)
    value = sa.Column(sa.Float(precision=2), nullable=False)

    @declared_attr
    def ecosystem_id(cls):
        return sa.Column(sa.String(length=8), sa.ForeignKey("ecosystems.id"),
                         nullable=False)

    @declared_attr
    def sensor_id(cls):
        return sa.Column(sa.String(length=16), sa.ForeignKey("hardware.id"),
                         nullable=False)

    __table_args__ = (
        UniqueConstraint("measure", "datetime", "value", "ecosystem_id",
                         "sensor_id", name="_no_repost_constraint"),
    )


class BaseActuatorData(Base):
    __abstract__ = True
    id = sa.Column(sa.Integer, primary_key=True)
    ecosystem_uid = sa.Column(sa.String(length=8))
    actuator_type = sa.Column(sa.String(length=16))
    datetime = sa.Column(sa.DateTime, nullable=False)
    mode = sa.Column(sa.String(length=16))
    status = sa.Column(sa.Boolean)

    @declared_attr
    def ecosystem_id(cls):
        return sa.Column(sa.String(length=8), sa.ForeignKey("ecosystems.id"),
                         index=True, primary_key=True)


class BaseHealthData(Base):
    __abstract__ = True
    datetime = sa.Column(sa.DateTime, nullable=False, primary_key=True)
    green = sa.Column(sa.Integer)
    necrosis = sa.Column(sa.Integer)
    health_index = sa.Column(sa.Float(precision=1))

    @declared_attr
    def ecosystem_id(cls):
        return sa.Column(sa.String(length=8), sa.ForeignKey("ecosystems.id"),
                         index=True, primary_key=True)


class BaseEcosystemWarning(Base):
    __abstract__ = True
    id = sa.Column(sa.Integer, primary_key=True)
    emergency = sa.Column(sa.Integer)
    level = sa.Column(sa.String(length=16))
    title = sa.Column(sa.String(length=256))
    description = sa.Column(sa.String(length=2048))
    content = sa.Column(sa.String)
    message = sa.Column(sa.String)  # TODO: change by description
    created = sa.Column(sa.DateTime)
    seen = sa.Column(sa.DateTime)
    solved = sa.Column(sa.DateTime)


class BaseSystemData(Base):
    __abstract__ = True
    id = sa.Column(sa.Integer, primary_key=True)
    datetime = sa.Column(sa.DateTime, nullable=False)
    CPU_used = sa.Column(sa.Float(precision=1))
    CPU_temp = sa.Column(sa.Float(precision=1))
    RAM_total = sa.Column(sa.Float(precision=2))
    RAM_used = sa.Column(sa.Float(precision=2))
    DISK_total = sa.Column(sa.Float(precision=2))
    DISK_used = sa.Column(sa.Float(precision=2))


# ---------------------------------------------------------------------------
#   Main app-related models, located in db_main and db_archive
# ---------------------------------------------------------------------------
class EngineManager(Base):
    __tablename__ = "engine_managers"
    uid = sa.Column(sa.String(length=16), primary_key=True)
    sid = sa.Column(sa.String(length=32))
    registration_date = sa.Column(sa.DateTime)
    address = sa.Column(sa.String(length=24))
    last_seen = sa.Column(sa.DateTime)
    connected = sa.Column(sa.Boolean)  # TODO: remove? and use based on last_seen?

    # relationship
    ecosystem = orm.relationship("Ecosystem", back_populates="manager", lazy="dynamic")

    # TODO: finish and add in others
    def to_dict(self):
        return {
            "uid": self.uid,
            "sid": self.sid,
            "registration_date": self.registration_date,
            "address": self.address,
            "last_seen": self.last_seen,
            "connected": self.connected,
            "ecosystems": [{
                "uid": ecosystem.id,
                "name": ecosystem.name,
                "status": ecosystem.status,
                "last_seen": ecosystem.last_seen,
            } for ecosystem in self.ecosystem]
        }


Management = {
    "sensors": 1,
    "light": 2,
    "climate": 4,
    "watering": 8,
    "health": 16,
    "alarms": 32,
    "webcam": 64,
}


class Ecosystem(Base):
    __tablename__ = "ecosystems"
    id = sa.Column(sa.String(length=8), primary_key=True)
    name = sa.Column(sa.String(length=32))
    status = sa.Column(sa.Boolean, default=False)
    last_seen = sa.Column(sa.DateTime)
    management = sa.Column(sa.Integer)
    # TODO: update day_start and night_start based on config data + morning_start and morning_end
    day_start = sa.Column(sa.Time, default=time(8, 00))
    night_start = sa.Column(sa.Time, default=time(20, 00))
    manager_uid = sa.Column(sa.Integer, sa.ForeignKey("engine_managers.uid"))

    # relationship
    manager = orm.relationship("EngineManager", back_populates="ecosystem")
    environment_parameters = orm.relationship("EnvironmentParameter", back_populates="ecosystem")
    hardware = orm.relationship("Hardware", back_populates="ecosystem", lazy="dynamic")
    plants = orm.relationship("Plant", back_populates="ecosystem", lazy="dynamic")
    # TODO: rename data to sensor_data
    data = orm.relationship("SensorData", back_populates="ecosystem", lazy="dynamic")
    actuator_data = orm.relationship("ActuatorData", back_populates="ecosystem", lazy="dynamic")
    health_data = orm.relationship("HealthData", back_populates="ecosystem", lazy="dynamic")
    light = orm.relationship("Light", back_populates="ecosystem", lazy="dynamic")

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

    def to_dict(self):
        return {
            "uid": self.id,
            "name": self.name,
            "manager_uid": self.manager_uid,
            "status": self.status,
            "last_seen": self.last_seen,
            "connected": self.manager.connected,
            "day_start": self.day_start,
            "night_start": self.night_start,
        }


class EnvironmentParameter(Base):
    __tablename__ = "environment_parameters"
    ecosystem_id = sa.Column(sa.String(length=8), sa.ForeignKey("ecosystems.id"),
                             primary_key=True)
    parameter = sa.Column(sa.String(length=16), primary_key=True)
    day = sa.Column(sa.Float(precision=2))
    night = sa.Column(sa.Float(precision=2))
    hysteresis = sa.Column(sa.Float(precision=2))

    # relationship
    ecosystem = orm.relationship("Ecosystem", back_populates="environment_parameters")

    def to_dict(self, display_ecosystem_uid=False):
        rv = {
            "parameter": self.parameter,
            "day": self.day,
            "night": self.night,
            "hysteresis": self.hysteresis,
        }
        if display_ecosystem_uid:
            return {**{"ecosystem_uid": self.ecosystem_id}, **rv}
        return rv


associationHardwareMeasure = db.Table(
    "association_hardware_measures", Base.metadata,
    sa.Column('hardware_id',
              sa.String(length=32),
              sa.ForeignKey('hardware.id')),
    sa.Column('measure_name',
              sa.Integer,
              sa.ForeignKey('measures.name')),
)


class Hardware(Base):
    __tablename__ = "hardware"
    id = sa.Column(sa.String(length=32), primary_key=True)
    ecosystem_id = sa.Column(sa.String(length=8),
                             sa.ForeignKey("ecosystems.id"), primary_key=True)
    name = sa.Column(sa.String(length=32))
    level = sa.Column(sa.String(length=16))
    address = sa.Column(sa.String(length=16))
    type = sa.Column(sa.String(length=16))
    model = sa.Column(sa.String(length=32))
    last_log = sa.Column(sa.DateTime)
    plant_id = sa.Column(sa.String(8), sa.ForeignKey("plants.id"))

    # relationship
    ecosystem = orm.relationship("Ecosystem", back_populates="hardware")
    measure = orm.relationship("Measure", back_populates="hardware",
                               secondary=associationHardwareMeasure)
    plants = orm.relationship("Plant", back_populates="sensors")
    data = orm.relationship("SensorData", back_populates="sensor", lazy="dynamic")

    def to_dict(self, display_ecosystem_uid=False):
        rv = {
            "uid": self.id,
            "name": self.name,
            "address": self.address,
            "level": self.level,
            "type": self.type,
            "model": self.model,
            "last_log": self.last_log,
            "measures": [measure.name for measure in self.measure],
        }
        if display_ecosystem_uid:
            return {**{"ecosystem_uid": self.ecosystem_id}, **rv}
        return rv


sa.Index("idx_sensors_type", Hardware.type, Hardware.level)


class Measure(Base):
    __tablename__ = "measures"
    name = sa.Column(sa.String(length=16), primary_key=True)
    unit = sa.Column(sa.String(length=16))

    # relationship
    hardware = orm.relationship("Hardware", back_populates="measure",
                                secondary=associationHardwareMeasure)

    def to_dict(self):
        return {
            "name": self.name,
            "unit": self.unit,
            "sensors": [sensor.id for sensor in self.hardware],
        }


class Plant(Base):
    __tablename__ = "plants"
    id = sa.Column(sa.String(16), primary_key=True)
    name = sa.Column(sa.String(32))
    ecosystem_uid = sa.Column(sa.String(length=8), sa.ForeignKey("ecosystems.id"))
    species = sa.Column(sa.String(32), index=True, nullable=False)
    sowing_date = sa.Column(sa.DateTime)

    #relationship
    ecosystem = orm.relationship("Ecosystem", back_populates="plants")
    sensors = orm.relationship("Hardware", back_populates="plants")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "ecosystem_uid": self.ecosystem_uid,
            "species": self.species,
            "sowing_date": self.sowing_date,
            "sensors": [sensor.id for sensor in self.sensors],
        }


class SensorData(BaseSensorData):
    __tablename__ = "sensors_data"
    __archive_link__ = archive_link("sensor", "recent")

    # relationships
    ecosystem = orm.relationship("Ecosystem", back_populates="data")
    sensor = orm.relationship("Hardware", back_populates="data")


class ActuatorData(BaseActuatorData):
    __tablename__ = "actuators_data"
    __archive_link__ = archive_link("light", "recent")

    # relationships
    ecosystem = orm.relationship("Ecosystem", back_populates="actuator_data")


class Light(Base):
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

    def to_dict(self):
        return {
            "ecosystem_uid": self.ecosystem_id,
            "method": self.method,
            "mode": self.mode,
            "status": self.status,
            "morning_start": self.morning_start,
            "morning_end": self.morning_end,
            "evening_start": self.evening_start,
            "evening_end": self.evening_end,
        }


class HealthData(BaseHealthData):
    __tablename__ = "health_data"
    __archive_link__ = archive_link("health", "recent")

    # relationships
    ecosystem = orm.relationship("Ecosystem", back_populates="health_data")


# TODO: When problems solved, after x days: goes to archive
class EcosystemWarning(BaseEcosystemWarning):
    __tablename__ = "ecosystem_warnings"
    __archive_link__ = archive_link("ecosystem_warnings", "recent")


class System(BaseSystemData):
    __tablename__ = "system_data"
    __archive_link__ = archive_link("system", "recent")


# ---------------------------------------------------------------------------
#   Models used for archiving, located in db_archive
# ---------------------------------------------------------------------------
class ArchiveSensorData(BaseSensorData):
    __tablename__ = "sensors_archive"
    __bind_key__ = "archive"
    __archive_link__ = archive_link("sensor", "archive")

    ecosystem_id = sa.Column(sa.String(length=8), primary_key=True)
    sensor_id = sa.Column(sa.String(length=16), primary_key=True)


class ArchiveHealthData(BaseHealthData):
    __tablename__ = "health_archive"
    __bind_key__ = "archive"
    __archive_link__ = archive_link("health", "archive")

    ecosystem_id = sa.Column(sa.String(length=8), primary_key=True)


class ArchiveEcosystemWarning(BaseEcosystemWarning):
    __tablename__ = "warnings_archive"
    __bind_key__ = "archive"

    ecosystem_id = sa.Column(sa.String(length=8), primary_key=True)


class archiveSystem(BaseSystemData):
    __tablename__ = "system_archive"
    __bind_key__ = "archive"
    __archive_link__ = archive_link("system", "archive")
