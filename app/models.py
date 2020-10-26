from hashlib import md5
from datetime import datetime, time

from werkzeug.security import generate_password_hash, check_password_hash
from flask import current_app
from flask_login import UserMixin, AnonymousUserMixin

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
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True)
    default = db.Column(db.Boolean, default=False, index=True)
    permissions = db.Column(db.Integer)

    # relationship
    users = db.relationship("User", back_populates="role", lazy="dynamic")

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
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), index=True, unique=True)
    email = db.Column(db.String(120), index=True, unique=True)
    password_hash = db.Column(db.String(128))
    role_id = db.Column(db.Integer, db.ForeignKey("roles.id"))
    confirmed = db.Column(db.Boolean, default=False)
    firstname = db.Column(db.String(64), unique=True)
    lastname = db.Column(db.String(64), unique=True)
    last_seen = db.Column(db.DateTime, default=datetime.utcnow)
    notifications = db.Column(db.Boolean, default=False)
    telegram_chat_id = db.Column(db.String(16), unique=True)
    # relationship
    role = db.relationship("Role", back_populates="users")

    def __init__(self, **kwargs):
        super(User, self).__init__(**kwargs)
        if self.role is None:
            if self.email in current_app.config["GAIA_ADMIN"]:
                self.role = Role.query.filter_by(name="Administrator").first()
            else:
                self.role = Role.query.filter_by(default=True).first()

    def __repr__(self):
        return "<User {} | {} {} | {}>".fdbat(
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
        return "https://www.gravatar.com/avatar/{}?d=identicon&s={}".fdbat(
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
    id = db.Column(db.String(8), primary_key=True)
    name = db.Column(db.String(32))
    status = db.Column(db.Boolean, default=False)

    lighting = db.Column(db.Boolean, default=False)
    watering = db.Column(db.Boolean, default=False)
    climate = db.Column(db.Boolean, default=False)
    health = db.Column(db.Boolean, default=False)
    alarms = db.Column(db.Boolean, default=False)

    webcam = db.Column(db.String(8))

    day_start = db.Column(db.Time, default=time(8, 00))
    day_temperature = db.Column(db.Float(precision=1), default=22.0)
    day_humidity = db.Column(db.Integer, default=70.0)
    day_light = db.Column(db.Integer, default=0.0)

    night_start = db.Column(db.Time, default=time(20, 00))
    night_temperature = db.Column(db.Float(precision=1), default=17.0)
    night_humidity = db.Column(db.Integer, default=40.0)
    night_light = db.Column(db.Integer, default=0.0)

    temperature_hysteresis = db.Column(db.Float(precision=1), default=1.0)
    humidity_hysteresis = db.Column(db.Integer, default=1.0)
    light_hysteresis = db.Column(db.Integer, default=0.0)
    # relationship
    hardware = db.relationship("Hardware", back_populates="ecosystem", lazy="dynamic")
    # plants = db.relationship("Plant", back_populates="ecosystem")
    data = db.relationship("Data", back_populates="ecosystem", lazy="dynamic")
    health_data = db.relationship("Health", back_populates="ecosystem", lazy="dynamic")
    light = db.relationship("Light", back_populates="ecosystem", lazy="dynamic")


class Hardware(db.Model):
    __tablename__ = "hardware"
    id = db.Column(db.String(32), primary_key=True)
    ecosystem_id = db.Column(db.String(8), db.ForeignKey("ecosystems.id"))
    name = db.Column(db.String(32))
    level = db.Column(db.String(16))
    pin = db.Column(db.Integer)
    type = db.Column(db.String(16))
    model = db.Column(db.String(32))
    # plant_id = db.Column(db.String(8), db.ForeignKey("plants.id"))
    # relationship
    ecosystem = db.relationship("Ecosystem", back_populates="hardware")
    # plants = db.relationship("Plant", back_populates="sensors")
    data = db.relationship("Data", back_populates="sensor", lazy="dynamic")

db.Index("idx_sensors_type", Hardware.type, Hardware.level)


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
        return "<Plant: {}, species: {}, sowing date: {}>".fdbat(
            self.name, self.species, self.sowing_date)
"""


class Data(db.Model):
    __tablename__ = "data"
    row_id = db.Column(db.Integer, primary_key=True)
    ecosystem_id = db.Column(db.String(8), db.ForeignKey("ecosystems.id"), index=True)
    sensor_id = db.Column(db.String(16), db.ForeignKey("hardware.id"), index=True)
    measure = db.Column(db.Integer, index=True)
    datetime = db.Column(db.DateTime, index=True)
    value = db.Column(db.Float(precision=2))
    # relationships
    ecosystem = db.relationship("Ecosystem", back_populates="data")
    sensor = db.relationship("Hardware", back_populates="data")


class Light(db.Model):
    __tablename__ = "light"
    ecosystem_id = db.Column(db.String(8), db.ForeignKey("ecosystems.id"), primary_key=True)
    status = db.Column(db.Boolean)
    mode = db.Column(db.String(12))
    method = db.Column(db.String(12))
    morning_start = db.Column(db.Time)
    morning_end = db.Column(db.Time)
    evening_start = db.Column(db.Time)
    evening_end = db.Column(db.Time)
    # relationships
    ecosystem = db.relationship("Ecosystem", back_populates="light")


class Health(db.Model):
    __tablename__ = "health"
    row_id = db.Column(db.Integer, primary_key=True)
    ecosystem_id = db.Column(db.String(8), db.ForeignKey("ecosystems.id"))
    datetime = db.Column(db.DateTime, nullable=False)
    green = db.Column(db.Integer)
    necrosis = db.Column(db.Integer)
    health_index = db.Column(db.Float(precision=1))
    # relationships
    ecosystem = db.relationship("Ecosystem", back_populates="health_data")


class System(db.Model):
    __tablename__ = "system"
    row_id = db.Column(db.Integer, primary_key=True)
    datetime = db.Column(db.DateTime, nullable=False)
    CPU_used = db.Column(db.Float(precision=1))
    CPU_temp = db.Column(db.Integer)
    RAM_total = db.Column(db.Float(precision=2))
    RAM_used = db.Column(db.Float(precision=2))
    DISK_total = db.Column(db.Float(precision=2))
    DISK_used = db.Column(db.Float(precision=2))


"""
class Service(db.Model):
    __tablename__ = "services"
    row_id = db.Column(db.Integer, primary_key=True)
    webcam = db.Column(db.Boolean)
    notifications = db.Column(db.String(16))
"""
