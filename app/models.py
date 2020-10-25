from hashlib import md5
from datetime import datetime, time

from werkzeug.security import generate_password_hash, check_password_hash
from flask import current_app
from flask_login import UserMixin, AnonymousUserMixin

import sqlalchemy as sa
import sqlalchemy.orm as orm

from app import login_manager
from app import db


# ---------------------------------------------------------------------------
#   Users-related models
# ---------------------------------------------------------------------------
class Permission:
    VIEW = 1
    EDIT = 2
    OPERATE = 4
    ADMIN = 8


class Role(db.Model):
    __tablename__ = "roles"
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
        return "<Role {}>".format(self.name)


class User(UserMixin, db.Model):
    __tablename__ = "users"
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

    def __repr__(self):
        return "<User {} | {} {} | {}>".format(
            self.username, self.firstname, self.lastname, self.email)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def can(self, perm):
        return self.role is not None and self.role.has_permission(perm)

    @property
    def is_administrator(self):
        return self.can(Permission.ADMIN)

    def avatar(self, size):
        digest = md5(self.email.lower().encode("utf-8")).hexdigest()
        return "https://www.gravatar.com/avatar/{}?d=identicon&s={}".format(
            digest, size)


class AnonymousUser(AnonymousUserMixin):
    def can(self):
        return False

    @property
    def is_administrator(self):
        return False


login_manager.anonymous_user = AnonymousUser


@login_manager.user_loader
def load_user(id):
    return User.query.get(int(id))


# ---------------------------------------------------------------------------
#   Ecosystems-related models
# ---------------------------------------------------------------------------
class Ecosystem(db.Model):
    __tablename__ = "ecosystems"
    id = sa.Column(sa.String(8), primary_key=True)
    name = sa.Column(sa.String(32))
    status = sa.Column(sa.Boolean, default=False)

    lighting = sa.Column(sa.Boolean, default=False)
    watering = sa.Column(sa.Boolean, default=False)
    climate = sa.Column(sa.Boolean, default=False)
    health = sa.Column(sa.Boolean, default=False)
    alarms = sa.Column(sa.Boolean, default=False)

    webcam = sa.Column(sa.String(8))

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
    # relationship
    hardware = orm.relationship("Hardware", back_populates="ecosystem", lazy="dynamic")
    # plants = orm.relationship("Plant", back_populates="ecosystem")
    data = orm.relationship("Data", back_populates="ecosystem", lazy="dynamic")
    health_data = orm.relationship("Health", back_populates="ecosystem", lazy="dynamic")
    light = orm.relationship("Light", back_populates="ecosystem", lazy="dynamic")


class Hardware(db.Model):
    __tablename__ = "hardware"
    id = sa.Column(sa.String(32), primary_key=True)
    ecosystem_id = sa.Column(sa.String(8), sa.ForeignKey("ecosystems.id"))
    name = sa.Column(sa.String(32))
    level = sa.Column(sa.String(16))
    pin = sa.Column(sa.Integer)
    type = sa.Column(sa.String(16))
    model = sa.Column(sa.String(32))
    # plant_id = sa.Column(sa.String(8), sa.ForeignKey("plants.id"))
    # relationship
    ecosystem = orm.relationship("Ecosystem", back_populates="hardware")
    # plants = orm.relationship("Plant", back_populates="sensors")
    data = orm.relationship("Data", back_populates="sensor", lazy="dynamic")

sa.Index("idx_sensors_type", Hardware.type, Hardware.level)


"""
class Plant(db.Model):
    __tablename__ = "plants"
    id = db.Column(db.String(16), primary_key=True)
    name = db.Column(db.String(32))
    ecosystem_id = db.Column(db.String(8), db.ForeignKey("ecosystems.id"))
    species = db.Column(db.String(32), index=True, nullable=False)
    sowing_date = db.Column(db.DateTime)
    #relationship
    ecosystem = db.relationship("Ecosystem", back_populates="plants")
    sensors = db.relationship("Hardware", back_populates="plants")

    def __repr__(self):
        return "<Plant: {}, species: {}, sowing date: {}>".format(
            self.name, self.species, self.sowing_date)
"""


class Data(db.Model):
    __tablename__ = "data"
    row_id = sa.Column(sa.Integer, primary_key=True)
    ecosystem_id = sa.Column(sa.String(8), sa.ForeignKey("ecosystems.id"), index=True)
    sensor_id = sa.Column(sa.String(16), sa.ForeignKey("hardware.id"), index=True)
    measure = sa.Column(sa.Integer, index=True)
    datetime = sa.Column(sa.DateTime, index=True)
    value = sa.Column(sa.Float(precision=2))
    # relationships
    ecosystem = orm.relationship("Ecosystem", back_populates="data")
    sensor = orm.relationship("Hardware", back_populates="data")


class Light(db.Model):
    __tablename__ = "light"
    ecosystem_id = sa.Column(sa.String(8), sa.ForeignKey("ecosystems.id"), primary_key=True)
    status = sa.Column(sa.Boolean)
    mode = sa.Column(sa.String(12))
    method = sa.Column(sa.String(12))
    morning_start = sa.Column(sa.Time)
    morning_end = sa.Column(sa.Time)
    evening_start = sa.Column(sa.Time)
    evening_end = sa.Column(sa.Time)
    # relationships
    ecosystem = orm.relationship("Ecosystem", back_populates="light")


class Health(db.Model):
    __tablename__ = "health"
    row_id = sa.Column(sa.Integer, primary_key=True)
    ecosystem_id = sa.Column(sa.String(8), sa.ForeignKey("ecosystems.id"))
    datetime = sa.Column(sa.DateTime, nullable=False)
    green = sa.Column(sa.Integer)
    necrosis = sa.Column(sa.Integer)
    health_index = sa.Column(sa.Float(precision=1))
    # relationships
    ecosystem = orm.relationship("Ecosystem", back_populates="health_data")


class System(db.Model):
    __tablename__ = "system"
    row_id = sa.Column(sa.Integer, primary_key=True)
    datetime = sa.Column(sa.DateTime, nullable=False)
    CPU_used = sa.Column(sa.Float(precision=1))
    CPU_temp = sa.Column(sa.Integer)
    RAM_total = sa.Column(sa.Float(precision=2))
    RAM_used = sa.Column(sa.Float(precision=2))
    DISK_total = sa.Column(sa.Float(precision=2))
    DISK_used = sa.Column(sa.Float(precision=2))


"""
class Service(db.Model):
    __tablename__ = "services"
    row_id = db.Column(db.Integer, primary_key=True)
    webcam = db.Column(db.Boolean)
    notifications = db.Column(db.String(16))
"""
