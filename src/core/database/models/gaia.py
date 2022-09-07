from datetime import time

import sqlalchemy as sa
from sqlalchemy import orm, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.schema import Table


from ._base import ArchiveLink, base
from .common import (
    BaseActuatorHistory, BaseHealth, BaseSensorHistory, BaseWarning
)
from src.core.utils import time_to_datetime


# ---------------------------------------------------------------------------
#   Ecosystems-related models, located in db_main and db_archive
# ---------------------------------------------------------------------------
Management = {
    "sensors": 1,
    "light": 2,
    "climate": 4,
    "watering": 8,
    "health": 16,
    "alarms": 32,
    "webcam": 64,
}


class Engine(base):
    __tablename__ = "engines"
    uid = sa.Column(sa.String(length=16), primary_key=True)
    sid = sa.Column(sa.String(length=32))
    registration_date = sa.Column(sa.DateTime)
    address = sa.Column(sa.String(length=24))
    last_seen = sa.Column(sa.DateTime)
    connected = sa.Column(sa.Boolean)

    # relationship
    ecosystems = orm.relationship("Ecosystem", back_populates="engine")  # , lazy="joined")

    # TODO: finish and add in others
    def to_dict(self):
        return {
            "uid": self.uid,
            "sid": self.sid,
            "registration_date": self.registration_date,
            "address": self.address,
            "last_seen": self.last_seen,
            "connected": self.connected,
            # "ecosystems": [ecosystem.uid for ecosystem in self.ecosystems]  # TODO
        }


class Ecosystem(base):
    __tablename__ = "ecosystems"
    uid = sa.Column(sa.String(length=8), primary_key=True)
    name = sa.Column(sa.String(length=32))
    status = sa.Column(sa.Boolean, default=False)
    last_seen = sa.Column(sa.DateTime)
    management = sa.Column(sa.Integer, default = 0)
    day_start = sa.Column(sa.Time, default=time(8, 00))
    night_start = sa.Column(sa.Time, default=time(20, 00))
    engine_uid = sa.Column(sa.Integer, sa.ForeignKey("engines.uid"))

    # relationship
    engine: "Engine" = orm.relationship("Engine", back_populates="ecosystems", lazy="joined")
    light = orm.relationship("Light", back_populates="ecosystem", lazy="joined", uselist=False)
    environment_parameters = orm.relationship("EnvironmentParameter", back_populates="ecosystem", lazy="joined")
    plants = orm.relationship("Plant", back_populates="ecosystem")
    hardware = orm.relationship("Hardware", back_populates="ecosystem")
    sensors_history = orm.relationship("SensorHistory", back_populates="ecosystem")
    actuators_history = orm.relationship("ActuatorHistory", back_populates="ecosystem")
    health = orm.relationship("Health", back_populates="ecosystem")

    def can_manage(self, mng):
        return self.management & mng == mng

    def add_management(self, mng):
        if not self.can_manage(mng):
            self.management += mng

    def remove_management(self, mng):
        if self.can_manage(mng):
            self.management -= mng

    def reset_managements(self):
        self.management = 0

    def to_dict(self):
        return {
            "uid": self.uid,
            "name": self.name,
            "status": self.status,
            "last_seen": self.last_seen,
            "connected": self.engine.connected,
            "engine_uid": self.engine_uid,
        }

    def management_dict(self):
        return {
            management: self.can_manage(value) for
            management, value in Management.items()
        }


class EnvironmentParameter(base):
    __tablename__ = "environment_parameters"
    ecosystem_uid = sa.Column(sa.String(length=8), sa.ForeignKey("ecosystems.uid"),
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
            rv.update({"ecosystem_uid": self.ecosystem_uid})
        return rv


associationHardwareMeasure = Table(
    "association_hardware_measures", base.metadata,
    sa.Column('hardware_uid',
              sa.String(length=32),
              sa.ForeignKey('hardware.uid')),
    sa.Column('measure_name',
              sa.Integer,
              sa.ForeignKey('measures.name')),
)


class Hardware(base):
    # TODO: add an "active" field which would be based on config?
    __tablename__ = "hardware"
    uid = sa.Column(sa.String(length=32), primary_key=True)
    ecosystem_uid = sa.Column(sa.String(length=8),
                              sa.ForeignKey("ecosystems.uid"), primary_key=True)
    name = sa.Column(sa.String(length=32))
    level = sa.Column(sa.String(length=16))
    address = sa.Column(sa.String(length=16))
    type = sa.Column(sa.String(length=16))
    model = sa.Column(sa.String(length=32))
    last_log = sa.Column(sa.DateTime)
    plant_uid = sa.Column(sa.String(8), sa.ForeignKey("plants.uid"))

    # relationship
    ecosystem = orm.relationship("Ecosystem", back_populates="hardware")
    measure = orm.relationship("Measure", back_populates="hardware",
                               secondary=associationHardwareMeasure,
                               lazy="joined")
    plants = orm.relationship("Plant", back_populates="sensors")
    sensors_history = orm.relationship("SensorHistory", back_populates="sensor",
                                       lazy="dynamic")

    def __repr__(self) -> str:
        return (
            f"Hardware({self.uid}, name={self.name}, "
            f"ecosystem={self.ecosystem_uid})"
        )

    def to_dict(self):
        rv = {
            "uid": self.uid,
            "name": self.name,
            "address": self.address,
            "level": self.level,
            "type": self.type,
            "model": self.model,
            "last_log": self.last_log,
            "ecosystem_uid": self.ecosystem_uid
        }
        if self.type == "sensor":
            rv.update({"measures": [measure.name for measure in self.measure]})
        return rv


sa.Index("idx_sensors_type", Hardware.type, Hardware.level)


class Measure(base):
    __tablename__ = "measures"
    id = sa.Column(sa.Integer, primary_key=True)
    name = sa.Column(sa.String(length=16))
    unit = sa.Column(sa.String(length=16))

    # relationship
    hardware = orm.relationship("Hardware", back_populates="measure",
                                secondary=associationHardwareMeasure)

    @staticmethod
    async def insert_measures(session: AsyncSession):
        measures = {
            "temperature": "°C",
            "humidity": "% humidity",
            "dew point": "°C",
            "absolute humidity": "°C",
            "moisture": "°C"
        }
        for name, unit in measures.items():
            stmt = select(Measure).where(Measure.name == name)
            result = await session.execute(stmt)
            measure = result.first()
            if not measure:
                m = Measure(name=name, unit=unit)
                session.add(m)
        await session.commit()

    def to_dict(self):
        return {
            "name": self.name,
            "unit": self.unit,
            # "sensors": [sensor.uid for sensor in self.hardware],
        }


class Plant(base):
    __tablename__ = "plants"
    uid = sa.Column(sa.String(16), primary_key=True)
    name = sa.Column(sa.String(32))
    ecosystem_uid = sa.Column(sa.String(length=8), sa.ForeignKey("ecosystems.uid"))
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
            "sensors": [sensor.uid for sensor in self.sensors],
        }


class SensorHistory(BaseSensorHistory):
    __tablename__ = "sensors_history"
    __archive_link__ = ArchiveLink("sensor", "recent")

    # relationships
    ecosystem = orm.relationship("Ecosystem", back_populates="sensors_history")
    sensor = orm.relationship("Hardware", back_populates="sensors_history")


class ActuatorHistory(BaseActuatorHistory):
    __tablename__ = "actuators_history"
    __archive_link__ = ArchiveLink("actuator", "recent")

    # relationships
    ecosystem = orm.relationship("Ecosystem", back_populates="actuators_history")


class Light(base):
    __tablename__ = "lights"
    id = sa.Column(sa.Integer, primary_key=True)
    status = sa.Column(sa.Boolean)
    mode = sa.Column(sa.String(length=12))
    method = sa.Column(sa.String(length=12))
    morning_start = sa.Column(sa.Time)
    morning_end = sa.Column(sa.Time)
    evening_start = sa.Column(sa.Time)
    evening_end = sa.Column(sa.Time)
    ecosystem_uid = sa.Column(sa.String(length=8), sa.ForeignKey("ecosystems.uid"))

    # relationships
    ecosystem: "Ecosystem" = orm.relationship("Ecosystem", back_populates="light")

    def to_dict(self):
        return {
            "ecosystem_uid": self.ecosystem_uid,
            "ecosystem_name": self.ecosystem.name,
            "method": self.method,
            "mode": self.mode,
            "status": self.status,
            "morning_start": time_to_datetime(self.morning_start),
            "morning_end": time_to_datetime(self.morning_end),
            "evening_start": time_to_datetime(self.evening_start),
            "evening_end": time_to_datetime(self.evening_end),
        }


class Health(BaseHealth):
    __tablename__ = "health"
    __archive_link__ = ArchiveLink("health", "recent")

    # relationships
    ecosystem = orm.relationship("Ecosystem", back_populates="health")


class GaiaWarning(BaseWarning):
    __tablename__ = "warnings"
    __archive_link__ = ArchiveLink("warnings", "recent")
