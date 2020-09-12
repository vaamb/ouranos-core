from hashlib import md5
from datetime import datetime, time

import sqlalchemy as db
from werkzeug.security import generate_password_hash, check_password_hash
from flask import current_app
from flask_login import UserMixin, AnonymousUserMixin

from app import login_manager
from app.database import Base, db_session



"""
Website models
"""
class Permission:
    VIEW = 1
    EDIT = 2
    OPERATE = 4
    ADMIN = 8


class Role(Base):
    __tablename__ = "roles"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True)
    default = db.Column(db.Boolean, default=False, index=True)
    permissions = db.Column(db.Integer)
    
    #relationship
    users = db.orm.relationship('User', back_populates='role', lazy='dynamic')

    def __init__(self, **kwargs):
        super(Role, self).__init__(**kwargs)
        if self.permissions is None:
            self.permissions = 0

    @staticmethod
    def insert_roles():
        roles = {
            'User': [Permission.VIEW, Permission.EDIT],
            'Operator': [Permission.VIEW, Permission.EDIT, 
                         Permission.OPERATE],
            'Administrator': [Permission.VIEW, Permission.EDIT,
                              Permission.OPERATE, Permission.ADMIN],
            }
        default_role = 'User'
        for r in roles:
            role = Role.query.filter_by(name=r).first()
            if role is None:
                role = Role(name=r)
            role.reset_permissions()
            for perm in roles[r]:
                role.add_permission(perm)
            role.default = (role.name == default_role)
            db_session.add(role)
        db_session.commit()

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
        return '<Role {}>'.format(self.name)


class User(UserMixin, Base):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), index=True, unique=True)
    email = db.Column(db.String(120), index=True, unique=True)
    password_hash = db.Column(db.String(128))
    role_id = db.Column(db.Integer, db.ForeignKey('roles.id'))
    confirmed = db.Column(db.Boolean, default=False)
    firstname = db.Column(db.String(64), index=True, unique=True)
    lastname = db.Column(db.String(64), index=True, unique=True)
    last_seen = db.Column(db.DateTime, default=datetime.utcnow)

    #relationship
    role = db.orm.relationship('Role', back_populates='users')    

    def __init__(self, **kwargs):
        super(User, self).__init__(**kwargs)
        if self.role is None:
            if self.email in current_app.config['GAIA_ADMIN']:
                self.role = Role.query.filter_by(name='Administrator').first()
            else:
                self.role = Role.query.filter_by(default=True).first()

    def __repr__(self):
        return '<User {} | {} {} | {}>'.format(
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
        digest = md5(self.email.lower().encode('utf-8')).hexdigest()
        return 'https://www.gravatar.com/avatar/{}?d=identicon&s={}'.format(
            digest, size)


class AnonymousUser(AnonymousUserMixin):
    def can(self, permissions):
        return False

    @property
    def is_administrator(self):
        return False

login_manager.anonymous_user = AnonymousUser

@login_manager.user_loader
def load_user(id):
    return User.query.get(int(id))


"""
Greenhouse management models
"""
class Ecosystem(Base):
    __tablename__ = "ecosystems"
    id = db.Column(db.String(8), primary_key=True)
    name = db.Column(db.String(32))
    status = db.Column(db.Boolean, default=False)
    lighting = db.Column(db.Boolean, default=False)
    light_level = db.Column(db.Boolean, default=False)
    watering = db.Column(db.Boolean, default=False)
    climate = db.Column(db.Boolean, default=False)
    webcam = db.Column(db.String(8))
    health = db.Column(db.Boolean, default=False)
    alarms = db.Column(db.Boolean, default=False)
    chaos = db.Column(db.Integer)
    day_start = db.Column(db.Time, default=time(8,00))
    day_temperature = db.Column(db.Float(precision=1), default=22.0)
    day_humidity = db.Column(db.Integer, default=70.0)
    day_light = db.Column(db.Integer, default=0.0)
    night_start = db.Column(db.Time, default=time(20,00))
    night_temperature = db.Column(db.Float(precision=1),default=17.0)
    night_humidity = db.Column(db.Integer, default=40.0)
    night_light = db.Column(db.Integer, default=0.0)
    temperature_hysteresis = db.Column(db.Float(precision=1), default=1.0)
    humidity_hysteresis = db.Column(db.Integer, default=1.0)
    light_hysteresis = db.Column(db.Integer, default=0.0)
    #relationship
    hardware = db.orm.relationship('Hardware', back_populates="ecosystem")
    plants = db.orm.relationship('Plant', back_populates="ecosystem")
    data = db.orm.relationship('Data', back_populates="ecosystem")
    health_data = db.orm.relationship('Health', back_populates="ecosystem")

    def __repr__(self):
        return '<Ecosystem {}>'.format(self.name)


class Hardware(Base):
    __tablename__ = "hardware"
    id = db.Column(db.String(16), primary_key=True)
    ecosystem_id = db.Column(db.String(8), db.ForeignKey('ecosystems.id'))
    name = db.Column(db.String(32))    
    level = db.Column(db.String(16))
    board_type = db.Column(db.String(5)) #either "BOARD" or BCM"
    pin = db.Column(db.Integer)
    type = db.Column(db.String(16))
    model = db.Column(db.String(32))
    measure_id = db.Column(db.String(16), db.ForeignKey('measures.id'))
    plant_id = db.Column(db.String(8), db.ForeignKey('plants.id'))
    #relationship
    ecosystem = db.orm.relationship('Ecosystem', back_populates="hardware")
    measure = db.orm.relationship('Measure', back_populates="sensors")
    plants = db.orm.relationship('Plant', back_populates="sensors")
    data = db.orm.relationship('Data', back_populates="sensor")

    def __repr__(self):
        return '<Sensor {}, model {}, measure {}>'.format(
            self.name, self.model, self.measure)


class Unit:
    temperature = ["°C"]
    humidity = ["% humidity"]
    light = ["lux", "PAR"]
    moisture = ["% humidity"]


class Measure(Base):
    __tablename__ = "measures"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(16), unique=True)
    unit = db.Column(db.String(16))
    #relationship
    sensors = db.orm.relationship('Hardware', back_populates="measure")

    @staticmethod
    def insert_measures():
        measures = {
            'temperature': Unit.temperature[0],
            'humidity': Unit.humidity[0],
            'light': Unit.light[0],
            "moisture": Unit.moisture[0],
            }
        for m in measures:
            measure = Measure.query.filter_by(name=m).first()
            if measure is None:
                measure = Measure(name=m, unit=measures[m])
            db_session.add(measure)
        db_session.commit()

    def __repr__(self):
        return '<Measure {}, unit {}>'.format(
            self.name, self.unit)


class Plant(Base):
    __tablename__ = "plants"
    id = db.Column(db.String(16), primary_key=True)
    name = db.Column(db.String(32))
    ecosystem_id = db.Column(db.String(8), db.ForeignKey('ecosystems.id'))
    species = db.Column(db.String(32), index=True, nullable=False)
    sowing_date = db.Column(db.DateTime)
    #relationship
    ecosystem = db.orm.relationship('Ecosystem', back_populates="plants")
    sensors = db.orm.relationship('Hardware', back_populates="plants")

    def __repr__(self):
        return '<Plant: {}, species: {}, sowing date: {}>'.format(
            self.name, self.species, self.sowing_date)


class Data(Base):
    __tablename__ = "data"
    row_id = db.Column(db.Integer, primary_key=True)
    level = db.Column(db.String(16), nullable=False)
    ecosystem_id = db.Column(db.String(8), db.ForeignKey('ecosystems.id'))
    sensor_id = db.Column(db.String(16), db.ForeignKey('hardware.id'))
    measure = db.Column(db.Integer, db.ForeignKey('measures.id'))
    datetime = db.Column(db.DateTime)
    value = db.Column(db.Float(precision=2))
    #relationships
    ecosystem = db.orm.relationship('Ecosystem', back_populates="data")
    sensor = db.orm.relationship('Hardware', back_populates="data")

    def __repr__(self):
        pass


class Health(Base):
    __tablename__ = "health"
    row_id = db.Column(db.Integer, primary_key=True)
    ecosystem_id = db.Column(db.String(8), db.ForeignKey('ecosystems.id'))
    datetime = db.Column(db.DateTime, nullable=False)
    green = db.Column(db.Integer)
    necrosis = db.Column(db.Integer)
    health_index = db.Column(db.Float(precision=1))
    #relationships
    ecosystem = db.orm.relationship('Ecosystem', back_populates="health_data")


class systemData(Base):
    __tablename__ = "system_data"
    row_id = db.Column(db.Integer, primary_key=True)
    datetime = db.Column(db.DateTime, nullable=False)
    CPU_used = db.Column(db.Float(precision=1))
    CPU_temp = db.Column(db.Integer)
    RAM_total = db.Column(db.Float(precision=2))
    RAM_used = db.Column(db.Float(precision=2))
    DISK_total = db.Column(db.Float(precision=2))
    DISK_used = db.Column(db.Float(precision=2))


class Service(Base):
    __tablename__ = "services"
    row_id = db.Column(db.Integer, primary_key=True)
    webcam = db.Column(db.Boolean)
    notifications = db.Column(db.String(16))