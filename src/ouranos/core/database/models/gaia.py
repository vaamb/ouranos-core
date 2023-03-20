from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from typing import Optional

import sqlalchemy as sa
from sqlalchemy import insert, select
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.schema import Table

from gaia_validators import (
    ClimateParameter, HardwareLevel, HardwareType, LightMethod, ManagementFlags
)

from ouranos.core.database import ArchiveLink
from ouranos.core.database.models.common import (
    ActuatorMode, base, BaseActuatorHistory, BaseHealth, BaseSensorHistory,
    BaseWarning
)
from ouranos.core.utils import time_to_datetime


# ---------------------------------------------------------------------------
#   Ecosystems-related models, located in db_main and db_archive
# ---------------------------------------------------------------------------
class Engine(base):
    __tablename__ = "engines"

    uid: Mapped[str] = mapped_column(sa.String(length=16), primary_key=True)
    sid: Mapped[str] = mapped_column(sa.String(length=32))
    registration_date: Mapped[datetime] = mapped_column()
    address: Mapped[Optional[str]] = mapped_column(sa.String(length=24))
    last_seen: Mapped[datetime] = mapped_column()

    # relationship
    ecosystems: Mapped[list["Ecosystem"]] = relationship(back_populates="engine", lazy="selectin")

    def __repr__(self):
        return f"<Engine({self.uid}, last_seen={self.last_seen})>"

    @property
    def connected(self) -> bool:
        return datetime.utcnow() - self.last_seen <= timedelta(seconds=30.0)


class Ecosystem(base):
    __tablename__ = "ecosystems"

    uid: Mapped[str] = mapped_column(sa.String(length=8), primary_key=True)
    name: Mapped[str] = mapped_column(sa.String(length=32))
    status: Mapped[bool] = mapped_column(default=False)
    last_seen: Mapped[datetime] = mapped_column(default=datetime.now(timezone.utc))
    management: Mapped[int] = mapped_column(default=0)
    day_start: Mapped[time] = mapped_column(default=time(8, 00))
    night_start: Mapped[time] = mapped_column(default=time(20, 00))
    engine_uid: Mapped[int] = mapped_column(sa.ForeignKey("engines.uid"))

    # relationship
    engine: Mapped["Engine"] = relationship(back_populates="ecosystems", lazy="selectin")
    light: Mapped["Light"] = relationship(back_populates="ecosystem", uselist=False)
    environment_parameters: Mapped[list["EnvironmentParameter"]] = relationship(back_populates="ecosystem")
    plants: Mapped[list["Plant"]] = relationship(back_populates="ecosystem")
    hardware: Mapped[list["Hardware"]] = relationship(back_populates="ecosystem")
    sensors_history: Mapped[list["SensorHistory"]] = relationship(back_populates="ecosystem")
    actuators_history: Mapped[list["ActuatorHistory"]] = relationship(back_populates="ecosystem")
    health: Mapped[list["Health"]] = relationship(back_populates="ecosystem")

    def __repr__(self):
        return (
            f"<Ecosystem({self.uid}, name={self.name}, status={self.status})>"
        )

    def can_manage(self, mng: ManagementFlags) -> bool:
        return self.management & mng.value == mng.value

    def add_management(self, mng: ManagementFlags) -> None:
        if not self.can_manage(mng):
            self.management += mng.value

    def remove_management(self, mng: ManagementFlags) -> None:
        if self.can_manage(mng):
            self.management -= mng.value

    def reset_managements(self):
        self.management = 0

    @property
    def connected(self) -> bool:
        return datetime.utcnow() - self.last_seen <= timedelta(seconds=30.0)


    def management_dict(self):
        return {
            management.name: self.can_manage(management) for
            management in ManagementFlags
        }


class EnvironmentParameter(base):
    __tablename__ = "environment_parameters"

    ecosystem_uid: Mapped[str] = mapped_column(sa.String(length=8), sa.ForeignKey("ecosystems.uid"), primary_key=True)
    parameter: Mapped[ClimateParameter] = mapped_column(primary_key=True)
    day: Mapped[float] = mapped_column(sa.Float(precision=2))
    night: Mapped[float] = mapped_column(sa.Float(precision=2))
    hysteresis: Mapped[float] = mapped_column(sa.Float(precision=2), default=0.0)

    # relationship
    ecosystem: Mapped["Ecosystem"] = relationship(back_populates="environment_parameters", lazy="selectin")


AssociationHardwareMeasure = Table(
    "association_hardware_measures", base.metadata,
    sa.Column("hardware_uid",
              sa.String(length=32),
              sa.ForeignKey("hardware.uid")),
    sa.Column("measure_name",
              sa.Integer,
              sa.ForeignKey("measures.name")),
)


AssociationSensorPlant = Table(
    "association_sensors_plants", base.metadata,
    sa.Column("sensor_uid",
              sa.String(length=32),
              sa.ForeignKey("hardware.uid")),
    sa.Column("plant_uid",
              sa.Integer,
              sa.ForeignKey("plants.uid")),
)


class Hardware(base):
    __tablename__ = "hardware"

    uid: Mapped[str] = mapped_column(sa.String(length=32), primary_key=True)
    ecosystem_uid: Mapped[str] = mapped_column(sa.String(length=8), sa.ForeignKey("ecosystems.uid"), primary_key=True)
    name: Mapped[str] = mapped_column(sa.String(length=32))
    level: Mapped[HardwareLevel] = mapped_column()
    address: Mapped[str] = mapped_column(sa.String(length=32))
    type: Mapped[HardwareType] = mapped_column(sa.String(length=16))
    model: Mapped[str] = mapped_column(sa.String(length=32))
    status: Mapped[bool] = mapped_column(default=True)
    last_log: Mapped[Optional[datetime]] = mapped_column()
    plant_uid: Mapped[Optional[str]] = mapped_column(sa.String(8), sa.ForeignKey("plants.uid"))

    # relationship
    ecosystem: Mapped["Ecosystem"] = relationship(back_populates="hardware")
    measures: Mapped[list["Measure"]] = relationship(
        back_populates="hardware", secondary=AssociationHardwareMeasure,
        lazy="selectin")
    plants: Mapped[list["Plant"]] = relationship(
        back_populates="sensors", secondary=AssociationSensorPlant,
        lazy="selectin")
    sensors_history: Mapped[list["SensorHistory"]] = relationship(
        back_populates="sensor")

    def __repr__(self) -> str:
        return (
            f"<Hardware({self.uid}, name={self.name}, "
            f"ecosystem_uid={self.ecosystem_uid})>"
        )


sa.Index("idx_sensors_type", Hardware.type, Hardware.level)


class Measure(base):
    __tablename__ = "measures"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(sa.String(length=16))
    unit: Mapped[str] = mapped_column(sa.String(length=16))

    # relationship
    hardware: Mapped[list["Hardware"]] = relationship(
        back_populates="measures", secondary=AssociationHardwareMeasure)

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
                stmt = insert(Measure).values({"name": name, "unit": unit})
                await session.execute(stmt)
        await session.commit()


class Plant(base):
    __tablename__ = "plants"
    uid: Mapped[str] = mapped_column(sa.String(16), primary_key=True)
    name: Mapped[str] = mapped_column(sa.String(32))
    ecosystem_uid: Mapped[str] = mapped_column(sa.String(length=8), sa.ForeignKey("ecosystems.uid"))
    species: Mapped[Optional[int]] = mapped_column(sa.String(32), index=True)
    sowing_date: Mapped[Optional[datetime]] = mapped_column()

    # relationship
    ecosystem = relationship("Ecosystem", back_populates="plants", lazy="selectin")
    sensors = relationship("Hardware", back_populates="plants",
                           secondary=AssociationSensorPlant,
                           lazy="selectin")


class SensorHistory(BaseSensorHistory):
    __tablename__ = "sensors_history"
    __archive_link__ = ArchiveLink("sensor", "recent")

    # relationships
    ecosystem: Mapped["Ecosystem"] = relationship(back_populates="sensors_history")
    sensor: Mapped["Hardware"] = relationship(back_populates="sensors_history")


class ActuatorHistory(BaseActuatorHistory):
    __tablename__ = "actuators_history"
    __archive_link__ = ArchiveLink("actuator", "recent")

    # relationships
    ecosystem: Mapped["Ecosystem"] = relationship(back_populates="actuators_history")


class Light(base):
    __tablename__ = "lights"

    id: Mapped[int] = mapped_column(primary_key=True)
    ecosystem_uid: Mapped[str] = mapped_column(sa.String(length=8), sa.ForeignKey("ecosystems.uid"))
    status: Mapped[bool] = mapped_column(default=False)
    mode: Mapped[ActuatorMode] = mapped_column(default=ActuatorMode.automatic)
    method: Mapped[LightMethod] = mapped_column(default=LightMethod.fixed)
    morning_start: Mapped[Optional[time]] = mapped_column()
    morning_end: Mapped[Optional[time]] = mapped_column()
    evening_start: Mapped[Optional[time]] = mapped_column()
    evening_end: Mapped[Optional[time]] = mapped_column()

    # relationships
    ecosystem: Mapped["Ecosystem"] = relationship(back_populates="light")


class Health(BaseHealth):
    __tablename__ = "health"
    __archive_link__ = ArchiveLink("health", "recent")

    # relationships
    ecosystem: Mapped["Ecosystem"] = relationship("Ecosystem", back_populates="health")


class GaiaWarning(BaseWarning):
    __tablename__ = "warnings"
    __archive_link__ = ArchiveLink("warnings", "recent")
