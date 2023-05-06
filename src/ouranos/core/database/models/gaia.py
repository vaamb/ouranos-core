from __future__ import annotations

from abc import abstractmethod
from datetime import datetime, time, timedelta, timezone
from typing import Literal, Optional, Sequence, Self, TypedDict

from asyncache import cached
from cachetools import LRUCache, TTLCache
from dispatcher import AsyncDispatcher
import sqlalchemy as sa
from sqlalchemy import delete, insert, select, update
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.schema import Table
from sqlalchemy.sql import func

from gaia_validators import (
    ActuatorTurnTo, ClimateParameter, HardwareLevel, HardwareLevelNames,
    HardwareType, HardwareTypeNames, IDs as EcosystemIDs, LightMethod,
    ManagementFlags)

from ouranos.core.database import ArchiveLink
from ouranos.core.database.models.common import (
    ActuatorMode, Base, BaseActuatorRecord, BaseHealthRecord, BaseSensorRecord,
    BaseWarning)
from ouranos.core.database.models.memory import SensorDbCache
from ouranos.core.database.models.types import UtcDateTime
from ouranos.core.database.models.utils import sessionless_hashkey, time_limits
from ouranos.core.utils import create_time_window, timeWindow


ActuatorTypeNames = Literal[
    "light", "heater", "cooler", "humidifier", "dehumidifier"
]
measure_order = (
    "temperature", "humidity", "lux", "dew_point", "absolute_moisture",
    "moisture"
)


_ecosystem_caches_size = 16
_cache_ecosystem_has_recent_data = TTLCache(maxsize=_ecosystem_caches_size * 2, ttl=60)
_cache_sensors_data_skeleton = TTLCache(maxsize=_ecosystem_caches_size, ttl=900)
_cache_sensor_records = TTLCache(maxsize=_ecosystem_caches_size * 32, ttl=900)
_cache_recent_warnings = TTLCache(maxsize=5, ttl=60)
_cache_measures = LRUCache(maxsize=16)


class EcosystemCurrentData(TypedDict):
    sensors: dict[str, dict[str, float]]
    timestamp: datetime


class GaiaBase(Base):
    __abstract__ = True

    uid: str | int

    @classmethod
    async def create(
            cls,
            session: AsyncSession,
            values: dict,
    ) -> Self:
        model = cls(**values)
        session.add(model)
        return model

    @classmethod
    async def update(
            cls,
            session: AsyncSession,
            values: dict,
            uid: str | None = None,
    ) -> None:
        uid = uid or values.pop("uid", None)
        if not uid:
            raise ValueError(
                "Provide uid either as a parameter or as a key in the updated info"
            )
        stmt = (
            update(cls)
            .where(cls.uid == uid)
            .values(**values)
        )
        await session.execute(stmt)

    @classmethod
    async def delete(
            cls,
            session: AsyncSession,
            uid: str,
    ) -> None:
        stmt = delete(cls).where(cls.uid == uid)
        await session.execute(stmt)

    @classmethod
    async def update_or_create(
            cls,
            session: AsyncSession,
            values: dict,
            uid: str | None = None,
    ) -> Self:
        uid = uid or values.pop("uid", None)
        if not uid:
            raise ValueError(
                "Provide uid either as an argument or as a key in the values"
            )
        obj = await cls.get(session, uid)
        if not obj:
            values["uid"] = uid
            obj = await cls.create(session, values)
        elif values:
            await cls.update(session, values, uid)
            obj = await cls.get(session, uid)
        return obj

    @classmethod
    @abstractmethod
    async def get(
            cls,
            session: AsyncSession,
            uid: str,
    ) -> Self | None:
        raise NotImplementedError

    @classmethod
    @abstractmethod
    async def get_multiple(
            cls,
            session: AsyncSession,
            uid: str | list | None = None,
    ) -> Sequence[Self]:
        raise NotImplementedError


# ---------------------------------------------------------------------------
#   Ecosystems-related models, located in db_main and db_archive
# ---------------------------------------------------------------------------
class Engine(GaiaBase):
    __tablename__ = "engines"

    uid: Mapped[str] = mapped_column(sa.String(length=16), primary_key=True)
    sid: Mapped[str] = mapped_column(sa.String(length=32))
    registration_date: Mapped[datetime] = mapped_column(UtcDateTime, default=func.current_timestamp())
    address: Mapped[Optional[str]] = mapped_column(sa.String(length=24))
    last_seen: Mapped[datetime] = mapped_column(UtcDateTime, onupdate=func.current_timestamp())

    # relationships
    ecosystems: Mapped[list["Ecosystem"]] = relationship(back_populates="engine", lazy="selectin")

    def __repr__(self):
        return f"<Engine({self.uid}, last_seen={self.last_seen})>"

    @property
    def connected(self) -> bool:
        return datetime.now(timezone.utc) - self.last_seen <= timedelta(seconds=30.0)

    @classmethod
    async def get(
            cls,
            session: AsyncSession,
            engine_id: str,
    ) -> Engine | None:
        stmt = select(Engine).where(
            (Engine.uid == engine_id)
            | (Engine.sid == engine_id)
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @classmethod
    async def get_multiple(
            cls,
            session: AsyncSession,
            engines: str | list | None = None,
    ) -> Sequence[Engine]:
        if engines is None:
            stmt = (
                select(cls)
                .order_by(cls.last_seen.desc())
            )
            result = await session.execute(stmt)
            return result.scalars().all()
        if isinstance(engines, str):
            engines = engines.split(",")
        if "recent" in engines:
            time_limit = time_limits("recent")
            stmt = (
                select(cls)
                .where(cls.last_seen >= time_limit)
                .order_by(cls.last_seen.desc())
            )
        elif "connected" in engines:
            stmt = (
                select(cls)
                .where(cls.connected == True)  # noqa
                .order_by(cls.uid.asc())
            )
        else:
            stmt = (
                select(cls)
                .where(
                    (cls.uid.in_(engines))
                    | (cls.sid.in_(engines))
                )
                .order_by(cls.uid.asc())
            )
        result = await session.execute(stmt)
        return result.scalars().all()


class Ecosystem(GaiaBase):
    __tablename__ = "ecosystems"

    uid: Mapped[str] = mapped_column(sa.String(length=8), primary_key=True)
    name: Mapped[str] = mapped_column(sa.String(length=32))
    status: Mapped[bool] = mapped_column(default=False)
    registration_date: Mapped[datetime] = mapped_column(UtcDateTime, default=func.current_timestamp())
    last_seen: Mapped[datetime] = mapped_column(UtcDateTime, onupdate=func.current_timestamp())
    management: Mapped[int] = mapped_column(default=0)
    day_start: Mapped[time] = mapped_column(default=time(8, 00))
    night_start: Mapped[time] = mapped_column(default=time(20, 00))
    engine_uid: Mapped[int] = mapped_column(sa.ForeignKey("engines.uid"))

    # relationships
    engine: Mapped["Engine"] = relationship(back_populates="ecosystems", lazy="selectin")
    light: Mapped["Light"] = relationship(back_populates="ecosystem", uselist=False)
    environment_parameters: Mapped[list["EnvironmentParameter"]] = relationship(back_populates="ecosystem")
    plants: Mapped[list["Plant"]] = relationship(back_populates="ecosystem")
    hardware: Mapped[list["Hardware"]] = relationship(back_populates="ecosystem")
    sensor_records: Mapped[list["SensorRecord"]] = relationship(back_populates="ecosystem")
    actuator_records: Mapped[list["ActuatorRecord"]] = relationship(back_populates="ecosystem")
    health_records: Mapped[list["HealthRecord"]] = relationship(back_populates="ecosystem")

    def __repr__(self):
        return (
            f"<Ecosystem({self.uid}, name={self.name}, status={self.status})>"
        )

    @property
    def ids(self) -> EcosystemIDs:
        return EcosystemIDs(self.uid, self.name)

    @property
    def connected(self) -> bool:
        return datetime.now(timezone.now) - self.last_seen <= timedelta(seconds=30.0)

    @property
    def management_dict(self):
        return {
            management.name: self.can_manage(management) for
            management in ManagementFlags
        }

    @classmethod
    async def get(
            cls,
            session: AsyncSession,
            ecosystem_id: str,
    ) -> Self | None:
        stmt = (
            select(cls)
            .where((cls.uid == ecosystem_id) | (cls.name == ecosystem_id))
        )
        result = await session.execute(stmt)
        return result.unique().scalar_one_or_none()

    @classmethod
    async def get_multiple(
            cls,
            session: AsyncSession,
            ecosystems: str | list[str] | None = None,
    ) -> Sequence[Ecosystem]:
        if ecosystems is None:
            stmt = (
                select(Ecosystem)
                .order_by(Ecosystem.name.asc(),
                          Ecosystem.last_seen.desc())
            )
            result = await session.execute(stmt)
            return result.scalars().all()

        if isinstance(ecosystems, str):
            ecosystems = ecosystems.split(",")
        if "recent" in ecosystems:
            time_limit = time_limits("recent")
            stmt = (
                select(Ecosystem)
                .where(Ecosystem.last_seen >= time_limit)
                .order_by(Ecosystem.status.desc(), Ecosystem.name.asc())
            )
        elif "connected" in ecosystems:
            stmt = (
                select(Ecosystem).join(Engine.ecosystems)
                .where(Engine.connected == True)  # noqa
                .order_by(Ecosystem.name.asc())
            )
        else:
            stmt = (
                select(Ecosystem)
                .where(Ecosystem.uid.in_(ecosystems) |
                       Ecosystem.name.in_(ecosystems))
                .order_by(Ecosystem.last_seen.desc(), Ecosystem.name.asc())
            )
        result = await session.execute(stmt)
        return result.scalars().all()

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

    @cached(_cache_ecosystem_has_recent_data)
    async def has_recent_sensor_data(
            self,
            session: AsyncSession,
            level: HardwareLevelNames,
            limits: datetime = time_limits("sensors"),
    ) -> bool:
        stmt = (
            select(Hardware)
            .where(Hardware.ecosystem_uid == self.uid)
            .where(
                Hardware.type == HardwareType.sensor.name,
                Hardware.level == level
            )
            .filter(Hardware.last_log >= limits)
        )
        result = await session.execute(stmt)
        return bool(result.first())

    async def functionalities(self, session: AsyncSession) -> dict:
        return {
            "uid": self.uid,
            "name": self.name,
            **self.management_dict,
            "switches": any((
                self.management_dict.get("climate"),
                self.management_dict.get("light")
            )),
            "environment_data": await self.has_recent_sensor_data(session, "environment"),
            "plants_data": await self.has_recent_sensor_data(session, "plants"),
        }

    @cached(_cache_sensors_data_skeleton, key=sessionless_hashkey)
    async def sensors_data_skeleton(
            self,
            session: AsyncSession,
            time_window: timeWindow,
            level: HardwareLevelNames | list[HardwareLevelNames] | None = None,
    ) -> dict:
        stmt = (
            select(Hardware).join(SensorRecord.sensor)
            .where(Hardware.ecosystem_uid == self.uid)
            .where(
                (SensorRecord.timestamp > time_window.start)
                & (SensorRecord.timestamp <= time_window.end)
            )
        )
        if level:
            if isinstance(level, str):
                level = level.split(",")
            stmt = stmt.where(Hardware.level.in_(level))
        result = await session.execute(stmt)
        sensor_objs: Sequence[Hardware] = result.unique().scalars().all()
        temp = {}
        for sensor_obj in sensor_objs:
            for measure_obj in sensor_obj.measures:
                try:
                    temp[measure_obj.name][sensor_obj.uid] = sensor_obj.name
                except KeyError:
                    temp[measure_obj.name] = {sensor_obj.uid: sensor_obj.name}
        skeleton = [{
            "measure": measure_name,
            "sensors": [{
                "uid": sensor_uid,
                "name": temp[measure_name][sensor_uid]
            } for sensor_uid in temp[measure_name]]
        } for measure_name in {
            key: temp[key] for key in measure_order if temp.get(key)
        }]
        return {
            "uid": self.uid,
            "name": self.name,
            "level": [i.name for i in HardwareLevel] if level is None else level,
            "sensors_skeleton": skeleton,
        }

    async def current_data(self, session: AsyncSession) -> Sequence[SensorDbCache]:
        return await SensorDbCache.get_recent(session, self.uid)

    async def turn_actuator(
            self,
            dispatcher: AsyncDispatcher,
            actuator: ActuatorTypeNames,
            mode: ActuatorTurnTo = "automatic",
            countdown: float = 0.0,
    ) -> None:
        # TODO: select room using db
        data = {
            "ecosystem_uid": self.uid,
            "actuator": actuator,
            "mode": mode,
            "countdown": countdown
        }
        await dispatcher.emit(
            event="turn_actuator", data=data, namespace="aggregator"
        )

    async def turn_light(
            self,
            dispatcher: AsyncDispatcher,
            mode: ActuatorTurnTo = "automatic",
            countdown: float = 0.0,
    ) -> None:
        await self.turn_actuator(
            dispatcher=dispatcher, actuator="light", mode=mode,
            countdown=countdown
        )


class Light(GaiaBase):
    __tablename__ = "lights"

    id: Mapped[int] = mapped_column(primary_key=True)
    ecosystem_uid: Mapped[str] = mapped_column(sa.ForeignKey("ecosystems.uid"))
    status: Mapped[bool] = mapped_column(default=False)
    mode: Mapped[ActuatorMode] = mapped_column(default=ActuatorMode.automatic)
    method: Mapped[LightMethod] = mapped_column(default=LightMethod.fixed)
    morning_start: Mapped[Optional[time]] = mapped_column()
    morning_end: Mapped[Optional[time]] = mapped_column()
    evening_start: Mapped[Optional[time]] = mapped_column()
    evening_end: Mapped[Optional[time]] = mapped_column()

    # relationships
    ecosystem: Mapped["Ecosystem"] = relationship(back_populates="light")

    @classmethod
    async def update(
            cls,
            session: AsyncSession,
            values: dict,
            ecosystem_uid: str | None = None,
    ) -> None:
        ecosystem_uid = ecosystem_uid or values.pop("ecosystem_uid", None)
        if not ecosystem_uid:
            raise ValueError(
                "Provide uid either as a parameter or as a key in the updated info"
            )
        stmt = (
            update(cls)
            .where(cls.ecosystem_uid == ecosystem_uid)
            .values(**values)
        )
        await session.execute(stmt)

    @classmethod
    async def get(
            cls,
            session: AsyncSession,
            ecosystem_uid: str,
    ) -> Self | None:
        stmt = select(cls).where(cls.ecosystem_uid == ecosystem_uid)
        result = await session.execute(stmt)
        return result.one_or_none()

    @classmethod
    async def get_multiple(
            cls,
            session: AsyncSession,
            ecosystem_uids: list[str] | None = None,
    ) -> Sequence[Self]:
        stmt = select(cls)
        if ecosystem_uids:
            stmt = stmt.where(cls.ecosystem_uid.in_(ecosystem_uids))
        result = await session.execute(stmt)
        return result.scalars().all()

    @classmethod
    async def update_or_create(
            cls,
            session: AsyncSession,
            values,
            ecosystem_uid: str | None = None,
    ) -> Light:
        ecosystem_uid = ecosystem_uid or values.pop("ecosystem_uid", None)
        if not ecosystem_uid:
            raise ValueError(
                "Provide ecosystem_uid either as an argument or as a key in the values"
            )
        obj = await cls.get(session, ecosystem_uid)
        if not obj:
            values["ecosystem_uid"] = ecosystem_uid
            obj = await cls.create(session, values)
        elif values:
            await cls.update(session, values, ecosystem_uid)
            obj = await cls.get(session, ecosystem_uid)
        return obj


class EnvironmentParameter(GaiaBase):
    __tablename__ = "environment_parameters"

    id: Mapped[int] = mapped_column(primary_key=True)
    ecosystem_uid: Mapped[str] = mapped_column(sa.String(length=8), sa.ForeignKey("ecosystems.uid"))
    parameter: Mapped[ClimateParameter] = mapped_column()
    day: Mapped[float] = mapped_column(sa.Float(precision=2))
    night: Mapped[float] = mapped_column(sa.Float(precision=2))
    hysteresis: Mapped[float] = mapped_column(sa.Float(precision=2), default=0.0)

    # relationships
    ecosystem: Mapped["Ecosystem"] = relationship(
        back_populates="environment_parameters", lazy="selectin")

    @classmethod
    async def update(
            cls,
            session: AsyncSession,
            parameter_info: dict,
            uid: str | None = None,
            parameter: str | None = None,
    ) -> None:
        uid = uid or parameter_info.pop("uid", None)
        parameter = parameter or parameter_info.pop("parameter", None)
        if not (uid and parameter):
            raise ValueError(
                "Provide uid and parameter either as a argument or as a key in the "
                "updated info"
            )
        stmt = (
            update(EnvironmentParameter)
            .where(
                EnvironmentParameter.ecosystem_uid == uid,
                EnvironmentParameter.parameter == parameter
            )
            .values(**parameter_info)
        )
        await session.execute(stmt)

    @classmethod
    async def delete(
            cls,
            session: AsyncSession,
            uid: str,
            parameter: str,
    ) -> None:
        stmt = (
            delete(EnvironmentParameter)
            .where(
                EnvironmentParameter.ecosystem_uid == uid,
                EnvironmentParameter.parameter == parameter
            )
        )
        await session.execute(stmt)

    @classmethod
    async def update_or_create(
            cls,
            session: AsyncSession,
            values: dict,
            uid: str | None = None,
    ) -> EnvironmentParameter:
        uid = uid or values.pop("uid", None)
        parameter = values.get("parameter")
        if not (uid and parameter):
            raise ValueError(
                "Provide uid and parameter either as a argument or as a key in the "
                "updated info"
            )
        environment_parameter = await cls.get(
            session, uid=uid, parameter=parameter
        )
        if not environment_parameter:
            values["ecosystem_uid"] = uid
            values["parameter"] = parameter
            environment_parameter = await cls.create(
                session, values
            )
        else:
            environment_parameter = await cls.update(
                session, values, uid
            )
        return environment_parameter

    @classmethod
    async def get(
            cls,
            session: AsyncSession,
            uid: str,
            parameter: str,
    ) -> Self | None:
        stmt = (
            select(cls)
            .where(cls.ecosystem_uid == uid)
            .where(cls.parameter == parameter)
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @classmethod
    async def get_multiple(
            cls,
            session: AsyncSession,
            uids: list | None = None,
            parameters: list | None = None,
    ) -> Sequence[Self]:
        stmt = select(cls)
        if uids:
            stmt = stmt.where(cls.ecosystem_uid.in_(uids))
        if parameters:
            stmt = stmt.where(cls.parameter.in_(parameters))
        result = await session.execute(stmt)
        return result.scalars().all()


AssociationHardwareMeasure = Table(
    "association_hardware_measures", Base.metadata,
    sa.Column("hardware_uid",
              sa.String(length=32),
              sa.ForeignKey("hardware.uid")),
    sa.Column("measure_name",
              sa.Integer,
              sa.ForeignKey("measures.name")),
)


AssociationActuatorPlant = Table(
    "association_actuators_plants", Base.metadata,
    sa.Column("sensor_uid",
              sa.String(length=32),
              sa.ForeignKey("hardware.uid")),
    sa.Column("plant_uid",
              sa.Integer,
              sa.ForeignKey("plants.uid")),
)


class Hardware(GaiaBase):
    __tablename__ = "hardware"

    uid: Mapped[str] = mapped_column(sa.String(length=32), primary_key=True)
    ecosystem_uid: Mapped[str] = mapped_column(
        sa.String(length=8), sa.ForeignKey("ecosystems.uid"), primary_key=True)
    name: Mapped[str] = mapped_column(sa.String(length=32))
    level: Mapped[HardwareLevel] = mapped_column()
    address: Mapped[str] = mapped_column(sa.String(length=32))
    type: Mapped[HardwareType] = mapped_column(sa.String(length=16))
    model: Mapped[str] = mapped_column(sa.String(length=32))
    status: Mapped[bool] = mapped_column(default=True)
    last_log: Mapped[Optional[datetime]] = mapped_column()
    plant_uid: Mapped[Optional[str]] = mapped_column(
        sa.String(8), sa.ForeignKey("plants.uid"))

    # relationships
    ecosystem: Mapped["Ecosystem"] = relationship(back_populates="hardware")
    measures: Mapped[list["Measure"]] = relationship(
        back_populates="hardware", secondary=AssociationHardwareMeasure,
        lazy="selectin")
    plants: Mapped[list["Plant"]] = relationship(
        back_populates="sensors", secondary=AssociationActuatorPlant,
        lazy="selectin")
    sensor_records: Mapped[list["SensorRecord"]] = relationship(
        back_populates="sensor")
    actuator_records: Mapped[list["ActuatorRecord"]] = relationship(
        back_populates="actuator")

    def __repr__(self) -> str:
        return (
            f"<Hardware({self.uid}, name={self.name}, "
            f"ecosystem_uid={self.ecosystem_uid})>"
        )

    async def attach_relationships(
            self,
            session: AsyncSession,
            measures: list | str,
            plants: list | str,
    ) -> None:
        for relative_list, relationship_cls, relationship_attr in (
                (measures, Measure, "measures"),
                (plants, Plant, "plants")
        ):
            if relative_list:
                if isinstance(relative_list, str):
                    relative_list = [relative_list]
                relative_list = [m.replace("_", " ") for m in relative_list]
                objs = await relationship_cls.get_multiple(
                    session, relative_list)
                relatives = getattr(self, relationship_attr)
                for obj in objs:
                    if obj not in relatives:
                        relatives.append(obj)
                session.add(self)

    @classmethod
    async def create(
            cls,
            session: AsyncSession,
            values: dict,
    ) -> Self:
        measures = values.pop("measures", [])
        plants = values.pop("plants", [])
        hardware_obj: Hardware = await super().create(session, values)
        if any((measures, plants)):
            await hardware_obj.attach_relationships(session, measures, plants)
        return hardware_obj

    @classmethod
    async def update(
            cls,
            session: AsyncSession,
            values: dict,
            uid: str | None = None,
    ) -> None:
        uid = uid or values.get("uid")
        measures = values.pop("measures", [])
        plants = values.pop("plants", [])
        await super().update(session, values, uid)
        if any((measures, plants)):
            hardware_obj = await cls.get(session, uid)
            await hardware_obj.attach_relationships(session, measures, plants)
            await session.commit()

    @classmethod
    async def get(
            cls,
            session: AsyncSession,
            hardware_uid: str,
    ) -> Hardware | None:
        stmt = select(Hardware).where(Hardware.uid == hardware_uid)
        result = await session.execute(stmt)
        return result.unique().scalars().one_or_none()

    @classmethod
    def generate_query(
            cls,
            hardware_uid: str | list | None = None,
            ecosystem_uid: str | list | None = None,
            level: HardwareLevelNames | list[HardwareLevelNames] | None = None,
            type: HardwareTypeNames | list[HardwareTypeNames] | None = None,
            model: str | list | None = None,
    ):
        uid = hardware_uid
        query = select(cls)
        local_vars = locals()
        args = "uid", "ecosystem_uid", "level", "type", "model"
        for arg in args:
            value = local_vars.get(arg)
            if value:
                if isinstance(value, str):
                    value = value.split(",")
                hardware_attr = getattr(cls, arg)
                query = query.where(hardware_attr.in_(value))
        return query

    @classmethod
    async def get_multiple(
            cls,
            session: AsyncSession,
            hardware_uids: str | list | None = None,
            ecosystem_uids: str | list | None = None,
            levels: HardwareLevelNames | list[HardwareLevelNames] | None = None,
            types: HardwareTypeNames | list[HardwareTypeNames] | None = None,
            models: str | list | None = None,
    ) -> Sequence[Hardware]:
        stmt = cls.generate_query(
            hardware_uids, ecosystem_uids, levels, types, models
        )
        result = await session.execute(stmt)
        return result.unique().scalars().all()

    @staticmethod
    def get_models_available() -> list:
        # TODO based on gaia / gaia-validators
        pass


sa.Index("idx_sensors_type", Hardware.type, Hardware.level)


class Sensor(Hardware):
    """Virtual Model class to handle Sensors, a specific type of hardware.

    Sensors creation, update and deletion are handled by the class `Hardware`
    """

    @staticmethod
    def _add_time_window_to_stmt(stmt, time_window: timeWindow):
        return (
            stmt.join(SensorRecord.sensor)
            .where(
                (SensorRecord.timestamp > time_window.start) &
                (SensorRecord.timestamp <= time_window.end)
            )
            .distinct()
        )

    @classmethod
    async def get(
            cls,
            session: AsyncSession,
            uid: str,
            time_window: timeWindow | None = None,
    ) -> Self | None:
        stmt = cls.generate_query(hardware_uid=uid)
        if time_window:
            stmt = cls._add_time_window_to_stmt(stmt, time_window)
        result = await session.execute(stmt)
        hardware: Hardware | None = result.unique().scalar_one_or_none()
        if hardware:
            if hardware.type != HardwareType.sensor.name:
                hardware = None
        return hardware

    @classmethod
    async def get_multiple(
            cls,
            session: AsyncSession,
            hardware_uids: str | list | None = None,
            ecosystem_uids: str | list | None = None,
            levels: HardwareLevelNames | list[HardwareLevelNames] | None = None,
            models: str | list | None = None,
            time_window: timeWindow = None,
    ) -> Sequence[Self]:
        stmt = cls.generate_query(
            hardware_uids, ecosystem_uids, levels, "sensor", models)
        if time_window:
            stmt = cls._add_time_window_to_stmt(stmt, time_window)
        result = await session.execute(stmt)
        hardware: Sequence[Hardware] = result.unique().scalars().all()
        return [h for h in hardware if h.type == HardwareType.sensor.name]

    async def _get_formatted_historic_data(
            self,
            session: AsyncSession,
            time_window: timeWindow,
            measures: str | list | None = None,
    ) -> list:
        if measures is None:
            measures = [measure.name for measure in self.measures]
        elif isinstance(measures, str):
            measures = measures.split(",")
        rv = []
        for measure in measures:
            records = await SensorRecord.get_records(
                session, self.uid, measure, time_window)
            if records:
                rv.append({
                    "measure": measure,
                    "unit": await Measure.get_unit(session, measure),
                    "records": [
                        (record.timestamp, record.value) for record in records
                    ],
                })
        return rv

    async def _get_formatted_current_data(
            self,
            session: AsyncSession,
            measures: str | list | None = None,
    ) -> list:
        if measures is None:
            measures = [measure.name for measure in self.measures]
        elif isinstance(measures, str):
            measures = measures.split(",")
        rv = []
        temp_data = await SensorDbCache.get_recent(
            session, sensor_uid=self.uid, measure=measures)
        for data in temp_data:
            rv.append({
                "measure": data.measure,
                "unit": await Measure.get_unit(session, data.measure),
                "value": data.value,
            })
        return rv

    async def get_overview(
            self,
            session: AsyncSession,
            measures: str | list | None = None,
            current_data: bool = True,
            historic_data: bool = True,
            time_window: timeWindow = None,
    ) -> dict:
        assert self.type == "sensor"
        rv = self.to_dict(exclude=["measure"])
        rv.update({"measures": [measure_obj.name for measure_obj in self.measures]})
        if current_data or historic_data:
            rv.update({"data": {}})
            if current_data:
                data = await self._get_formatted_current_data(session, measures)
                if data:
                    rv["data"].update({
                        "current": {
                            "data": data,
                        }
                    })
                else:
                    rv["data"].update({"current": None})
            if historic_data:
                if time_window:
                    restricted_time_window = create_time_window(
                        time_window.start, time_window.end)
                else:
                    restricted_time_window = create_time_window()
                data = await self._get_formatted_historic_data(
                    session, restricted_time_window, measures)
                if data:
                    rv["data"].update({
                        "historic": {
                            "from": time_window.start,
                            "to": time_window.end,
                            "data": data,
                        }
                    })
                else:
                    rv["data"].update({"historic": None})
        return rv

    @staticmethod
    async def create_records(
            session: AsyncSession,
            values: dict | list[dict],
    ) -> None:
        await SensorRecord.create_records(session, values)


class Actuator(Hardware):
    """Virtual Model class to handle Actuators, a specific type of hardware.

    Actuators creation, update and deletion are handled by the class `Hardware`
    """

    @staticmethod
    def _add_time_window_to_stmt(stmt, time_window: timeWindow):
        return (
            stmt.join(ActuatorRecord.actuator)
            .where(
                (ActuatorRecord.timestamp > time_window.start)
                & (ActuatorRecord.timestamp <= time_window.end)
            )
            .distinct()
        )

    @classmethod
    async def get(
            cls,
            session: AsyncSession,
            uid: str,
            time_window: timeWindow | None = None,
    ) -> Self | None:
        stmt = cls.generate_query(hardware_uid=uid)
        if time_window:
            stmt = cls._add_time_window_to_stmt(stmt, time_window)
        result = await session.execute(stmt)
        hardware: Hardware | None = result.unique().scalar_one_or_none()
        if hardware:
            if hardware.type == HardwareType.sensor.name:
                hardware = None
        return hardware

    @classmethod
    async def get_multiple(
            cls,
            session: AsyncSession,
            hardware_uids: str | list | None = None,
            ecosystem_uids: str | list | None = None,
            levels: HardwareLevelNames | list[HardwareLevelNames] | None = None,
            models: str | list | None = None,
            time_window: timeWindow = None,
    ) -> Sequence[Self]:
        stmt = cls.generate_query(
            hardware_uids, ecosystem_uids, levels, "sensor", models)
        if time_window:
            stmt = cls._add_time_window_to_stmt(stmt, time_window)
        result = await session.execute(stmt)
        hardware: Sequence[Hardware] = result.unique().scalars().all()
        return [h for h in hardware if h.type != HardwareType.sensor.name]


class Measure(GaiaBase):
    __tablename__ = "measures"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(sa.String(length=16))
    unit: Mapped[str] = mapped_column(sa.String(length=16))

    # relationships
    hardware: Mapped[list["Hardware"]] = relationship(
        back_populates="measures", secondary=AssociationHardwareMeasure)

    @classmethod
    async def insert_measures(cls, session: AsyncSession) -> None:
        measures = {
            "temperature": "°C",
            "humidity": "% humidity",
            "dew point": "°C",
            "absolute humidity": "°C",
            "moisture": "°C"
        }
        for name, unit in measures.items():
            stmt = select(cls).where(cls.name == name)
            result = await session.execute(stmt)
            measure = result.first()
            if not measure:
                stmt = insert(cls).values({"name": name, "unit": unit})
                await session.execute(stmt)
        await session.commit()

    @classmethod
    @cached(_cache_measures, key=sessionless_hashkey)
    async def get_unit(
            cls,
            session: AsyncSession,
            measure_name: str
    ) -> str | None:
        stmt = (
            select(cls)
            .filter(cls.name == measure_name)
        )
        result = await session.execute(stmt)
        measure_obj = result.scalars().one_or_none()
        if measure_obj is not None:
            return measure_obj.unit
        return None

    @classmethod
    async def get(
            cls,
            session: AsyncSession,
            name: str
    ) -> Self | None:
        stmt = select(cls).where(cls.name == name)
        result = await session.execute(stmt)
        return result.scalars().one_or_none()

    @classmethod
    async def get_multiple(
            cls,
            session: AsyncSession,
            names: list[str] | None = None
    ) -> Sequence[Self]:
        stmt = select(cls)
        if names:
            stmt = stmt.where(cls.name.in_(names))
        result = await session.execute(stmt)
        return result.scalars().all()


class Plant(GaiaBase):
    __tablename__ = "plants"
    uid: Mapped[str] = mapped_column(sa.String(16), primary_key=True)
    name: Mapped[str] = mapped_column(sa.String(32))
    ecosystem_uid: Mapped[str] = mapped_column(sa.String(length=8), sa.ForeignKey("ecosystems.uid"))
    species: Mapped[Optional[int]] = mapped_column(sa.String(32), index=True)
    sowing_date: Mapped[Optional[datetime]] = mapped_column()

    # relationships
    ecosystem = relationship("Ecosystem", back_populates="plants", lazy="selectin")
    sensors = relationship(
        "Hardware", back_populates="plants", secondary=AssociationActuatorPlant,
        lazy="selectin")

    @classmethod
    async def get(
            cls,
            session: AsyncSession,
            plant_id: str
    ) -> Self | None:
        stmt = select(cls).where(
            (cls.name.in_(plant_id))
            | (cls.uid.in_(plant_id))
        )
        result = await session.execute(stmt)
        return result.scalars().one_or_none()

    @classmethod
    async def get_multiple(
            cls,
            session: AsyncSession,
            plants_id: list[str] | None = None
    ) -> Sequence[Self]:
        stmt = select(cls)
        if plants_id:
            stmt = stmt.where(
                (cls.name.in_(plants_id))
                | (cls.uid.in_(plants_id))
            )
        result = await session.execute(stmt)
        return result.scalars().all()


class SensorRecord(BaseSensorRecord):
    __tablename__ = "sensor_records"
    __archive_link__ = ArchiveLink("sensor", "recent")

    # relationships
    ecosystem: Mapped["Ecosystem"] = relationship(back_populates="sensor_records")
    sensor: Mapped["Hardware"] = relationship(back_populates="sensor_records")

    @classmethod
    @cached(_cache_sensor_records)
    async def get_records(
            cls,
            session: AsyncSession,
            sensor_uid: str,
            measure_name: str,
            time_window: timeWindow
    ) -> Sequence[Self]:
        return await super().get_records(
            session, sensor_uid, measure_name, time_window)


class ActuatorRecord(BaseActuatorRecord):
    __tablename__ = "actuator_records"
    __archive_link__ = ArchiveLink("actuator", "recent")

    # relationships
    ecosystem: Mapped["Ecosystem"] = relationship(back_populates="actuator_records")
    actuator: Mapped["Hardware"] = relationship(back_populates="actuator_records")


class HealthRecord(BaseHealthRecord):
    __tablename__ = "health_records"
    __archive_link__ = ArchiveLink("health_records", "recent")

    # relationships
    ecosystem: Mapped["Ecosystem"] = relationship("Ecosystem", back_populates="health_records")


class GaiaWarning(BaseWarning):
    __tablename__ = "warnings"
    __archive_link__ = ArchiveLink("warnings", "recent")

    @classmethod
    @cached(_cache_recent_warnings, key=sessionless_hashkey)
    async def get_recent(
            cls,
            session: AsyncSession,
            limit: int = 10
    ) -> Sequence[Self]:
        time_limit = time_limits("warnings")
        stmt = (
            select(cls)
            .where(cls.created_on >= time_limit)
            .where(cls.solved == False)  # noqa
            .order_by(cls.level.desc())
            .order_by(cls.id)
            .limit(limit)
        )
        result = await session.execute(stmt)
        return result.scalars().all()
