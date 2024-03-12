from __future__ import annotations

from abc import abstractmethod
from datetime import datetime, time, timedelta, timezone
from typing import Optional, Sequence, Self, TypedDict
from uuid import UUID

from asyncache import cached
from cachetools import LRUCache, TTLCache
from dispatcher import AsyncDispatcher
import sqlalchemy as sa
from sqlalchemy import delete, insert, select, update
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.schema import Table
from sqlalchemy.sql import func

import gaia_validators as gv

from ouranos.core.database import ArchiveLink
from ouranos.core.database.models.common import (
    Base, BaseActuatorRecord, BaseHealthRecord, BaseSensorRecord, ImportanceLevel)
from ouranos.core.database.models.memory import SensorDbCache
from ouranos.core.database.models.types import UtcDateTime
from ouranos.core.database.models.utils import sessionless_hashkey, time_limits
from ouranos.core.utils import create_time_window, timeWindow


measure_order = (
    "temperature", "humidity", "lux", "dew_point", "absolute_moisture",
    "moisture"
)


_ecosystem_caches_size = 16
_cache_ecosystem_has_recent_data = TTLCache(maxsize=_ecosystem_caches_size * 2, ttl=60)
_cache_sensors_data_skeleton = TTLCache(maxsize=_ecosystem_caches_size, ttl=900)
_cache_sensor_values = TTLCache(maxsize=_ecosystem_caches_size * 32, ttl=600)
_cache_warnings = TTLCache(maxsize=5, ttl=60)
_cache_measures = LRUCache(maxsize=16)


class EcosystemCurrentData(TypedDict):
    sensors: dict[str, dict[str, float]]
    timestamp: datetime


class EcosystemActuatorTypesManagedDict(TypedDict):
    light: bool
    cooler: bool
    heater: bool
    humidifier: bool
    dehumidifier: bool


class GaiaBase(Base):
    __abstract__ = True

    uid: str | int

    @classmethod
    async def create(
            cls,
            session: AsyncSession,
            values: dict | list[dict],
    ) -> None:
        stmt = insert(cls).values(values)
        await session.execute(stmt)

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
    ) -> None:
        uid = uid or values.pop("uid", None)
        if not uid:
            raise ValueError(
                "Provide uid either as an argument or as a key in the values"
            )
        obj = await cls.get(session, uid)
        if not obj:
            values["uid"] = uid
            await cls.create(session, values)
        elif values:
            await cls.update(session, values, uid)
        else:
            raise ValueError

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


class InConfigMixin:
    in_config: Mapped[bool] = mapped_column(default=True)

    @classmethod
    @abstractmethod
    async def get_multiple(
            cls,
            session: AsyncSession,
            uid: str | list | None = None,
            in_config: bool | None = None
    ) -> Sequence[Self]:
        raise NotImplementedError


# ---------------------------------------------------------------------------
#   Ecosystems-related models, located in db_main and db_archive
# ---------------------------------------------------------------------------
class Engine(GaiaBase):
    __tablename__ = "engines"

    uid: Mapped[str] = mapped_column(sa.String(length=32), primary_key=True)
    sid: Mapped[UUID] = mapped_column()
    registration_date: Mapped[datetime] = mapped_column(UtcDateTime, default=func.current_timestamp())
    address: Mapped[Optional[str]] = mapped_column(sa.String(length=16))
    last_seen: Mapped[datetime] = mapped_column(UtcDateTime, default=func.current_timestamp())  # , onupdate=func.current_timestamp())

    # relationships
    ecosystems: Mapped[list["Ecosystem"]] = relationship(back_populates="engine", lazy="selectin")
    places: Mapped[list[Place]] = relationship(back_populates="engine")

    def __repr__(self):
        return f"<Engine({self.uid}, last_seen={self.last_seen})>"

    @property
    def connected(self) -> bool:
        return datetime.now(timezone.utc) - self.last_seen <= timedelta(seconds=30.0)

    @classmethod
    async def get(
            cls,
            session: AsyncSession,
            engine_id: str | UUID,
    ) -> Engine | None:
        if isinstance(engine_id, UUID):
            # Received an engine sid
            stmt = select(Engine).where(Engine.sid == engine_id)
        else:
            # Received an engine uid
            stmt = select(Engine).where(Engine.uid == engine_id)
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

    async def get_crud_requests(self, session: AsyncSession) -> Sequence[CrudRequest]:
        response = await CrudRequest.get_for_engine(session, self.uid)
        return response


class Ecosystem(InConfigMixin, GaiaBase):
    __tablename__ = "ecosystems"

    uid: Mapped[str] = mapped_column(sa.String(length=8), primary_key=True)
    name: Mapped[str] = mapped_column(sa.String(length=32), default="_registering")
    status: Mapped[bool] = mapped_column(default=False)
    registration_date: Mapped[datetime] = mapped_column(UtcDateTime, default=func.current_timestamp())
    last_seen: Mapped[datetime] = mapped_column(UtcDateTime, default=func.current_timestamp())  # , onupdate=func.current_timestamp())
    management: Mapped[int] = mapped_column(default=0)
    day_start: Mapped[time] = mapped_column(default=time(8, 00))
    night_start: Mapped[time] = mapped_column(default=time(20, 00))
    engine_uid: Mapped[UUID] = mapped_column(sa.ForeignKey("engines.uid"))

    # relationships
    engine: Mapped["Engine"] = relationship(back_populates="ecosystems", lazy="selectin")
    lighting: Mapped["Lighting"] = relationship(back_populates="ecosystem", uselist=False, lazy="selectin")
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
    def ids(self) -> gv.EcosystemIDs:
        return gv.EcosystemIDs(self.uid, self.name)

    @property
    def connected(self) -> bool:
        return datetime.now(timezone.utc) - self.last_seen <= timedelta(seconds=30.0)

    @property
    def management_dict(self):
        return {
            management.name: self.can_manage(management) for
            management in gv.ManagementFlags
        }

    @property
    def lighting_method(self) -> gv.LightMethod | None:
        try:
            return self.lighting.method
        except AttributeError:
            return None

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
            in_config: bool | None = None,
    ) -> Sequence[Ecosystem]:
        if ecosystems is None:
            stmt = (
                select(Ecosystem)
                .order_by(Ecosystem.name.asc(),
                          Ecosystem.last_seen.desc())
            )
            if in_config is not None:
                stmt = stmt.where(cls.in_config == in_config)
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
        if in_config is not None:
            stmt = stmt.where(cls.in_config == in_config)
        result = await session.execute(stmt)
        return result.scalars().all()

    def can_manage(self, mng: gv.ManagementFlags) -> bool:
        return self.management & mng.value == mng.value

    def add_management(self, mng: gv.ManagementFlags) -> None:
        if not self.can_manage(mng):
            self.management += mng.value

    def remove_management(self, mng: gv.ManagementFlags) -> None:
        if self.can_manage(mng):
            self.management -= mng.value

    def reset_managements(self):
        self.management = 0

    @cached(_cache_ecosystem_has_recent_data, key=sessionless_hashkey)
    async def has_recent_sensor_data(
            self,
            session: AsyncSession,
            level: gv.HardwareLevel,
            time_limit: datetime = time_limits("sensors"),
    ) -> bool:
        stmt = (
            select(Hardware)
            .where(Hardware.ecosystem_uid == self.uid)
            .where(
                Hardware.type == gv.HardwareType.sensor,
                Hardware.level == level
            )
            .filter(Hardware.last_log >= time_limit)
        )
        result = await session.execute(stmt)
        return bool(result.first())

    async def functionalities(self, session: AsyncSession) -> dict:
        return {
            "uid": self.uid,
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
            level: gv.HardwareLevel | list[gv.HardwareLevel] | None = None,
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
        stmt = stmt.group_by(Hardware.uid)
        result = await session.execute(stmt)
        sensor_objs: Sequence[Hardware] = result.unique().scalars().all()
        sensors_by_measure: dict[str, list[dict[str, str]]] = {}
        for sensor_obj in sensor_objs:
            for measure_obj in sensor_obj.measures:
                measure_obj: Measure
                sensor_summary: dict[str, str] = {
                    "uid": sensor_obj.uid,
                    "name": sensor_obj.name,
                    "unit": measure_obj.unit,
                }
                try:
                    sensors_by_measure[measure_obj.name].append(sensor_summary)
                except KeyError:
                    sensors_by_measure[measure_obj.name] = [sensor_summary]
        skeleton = []
        # Add common measures first
        for measure_name in measure_order:
            sensors_summary = sensors_by_measure.pop(measure_name, None)
            if sensors_summary:
                skeleton.append({
                    "measure": measure_name,
                    "units": list({sensor["unit"] for sensor in sensors_summary}),
                    "sensors": sensors_summary,
                })
        # Add less common measures afterwards
        for measure_name, sensors_summary in sensors_by_measure.items():
            skeleton.append({
                "measure": measure_name,
                "units": list({sensor["unit"] for sensor in sensors_summary}),
                "sensors": sensors_summary,
            })
        return {
            "uid": self.uid,
            "name": self.name,
            "level": [i.name for i in gv.HardwareLevel] if level is None else level,
            "sensors_skeleton": skeleton,
        }

    async def current_data(self, session: AsyncSession) -> Sequence[SensorDbCache]:
        return await SensorDbCache.get_recent(session, self.uid)

    async def actuators_status(
            self,
            session: AsyncSession
    ) -> EcosystemActuatorTypesManagedDict:
        stmt = (
            select(ActuatorStatus)
            .where(ActuatorStatus.ecosystem_uid == self.uid)
        )
        result = await session.execute(stmt)
        actuators_status = result.scalars().all()
        return {
            actuator.actuator_type.name: actuator
            for actuator in actuators_status
        }

    async def turn_actuator(
            self,
            dispatcher: AsyncDispatcher,
            actuator: gv.HardwareType,
            mode: gv.ActuatorModePayload = gv.ActuatorModePayload.automatic,
            countdown: float = 0.0,
    ) -> None:
        assert actuator in gv.HardwareType.actuator
        data = {
            "ecosystem_uid": self.uid,
            "actuator": actuator.name,
            "mode": mode.name,
            "countdown": countdown
        }
        await dispatcher.emit(
            event="turn_actuator", data=data, namespace="aggregator-internal")

    async def turn_light(
            self,
            dispatcher: AsyncDispatcher,
            mode: gv.ActuatorModePayload = gv.ActuatorModePayload.automatic,
            countdown: float = 0.0,
    ) -> None:
        await self.turn_actuator(
            dispatcher=dispatcher, actuator=gv.HardwareType.light, mode=mode,
            countdown=countdown)


class ActuatorStatus(GaiaBase):
    __tablename__ = "actuators_status"

    ecosystem_uid: Mapped[str] = mapped_column(sa.ForeignKey("ecosystems.uid"), primary_key=True)
    actuator_type: Mapped[gv.HardwareType] = mapped_column(primary_key=True)
    status: Mapped[bool] = mapped_column(default=False)
    mode: Mapped[gv.ActuatorMode] = mapped_column(default=gv.ActuatorMode.automatic)
    active: Mapped[bool] = mapped_column(default=False)

    @classmethod
    async def update(
            cls,
            session: AsyncSession,
            actuator_info: dict,
            ecosystem_uid: str | None = None,
            actuator_type: str | None = None,
    ) -> None:
        ecosystem_uid = ecosystem_uid or actuator_info.pop("ecosystem_uid", None)
        actuator_type = actuator_type or actuator_info.pop("actuator_type", None)
        if not (ecosystem_uid and actuator_type):
            raise ValueError(
                "Provide uid and actuator_type either as a argument or as a key in the "
                "updated info"
            )
        if not actuator_info:
            return
        stmt = (
            update(cls)
            .where(
                cls.ecosystem_uid == ecosystem_uid,
                cls.actuator_type == actuator_type
            )
            .values(**actuator_info)
        )
        await session.execute(stmt)

    @classmethod
    async def delete(
            cls,
            session: AsyncSession,
            ecosystem_uid: str,
            actuator_type: str,
    ) -> None:
        stmt = (
            delete(cls)
            .where(
                cls.ecosystem_uid == ecosystem_uid,
                cls.actuator_type == actuator_type,
            )
        )
        await session.execute(stmt)

    @classmethod
    async def update_or_create(
            cls,
            session: AsyncSession,
            values: dict,
            ecosystem_uid: str | None = None,
            actuator_type: str | None = None,
    ) -> None:
        ecosystem_uid = ecosystem_uid or values.pop("ecosystem_uid", None)
        actuator_type = actuator_type or values.pop("actuator_type", None)
        if not (ecosystem_uid and actuator_type):
            raise ValueError(
                "Provide uid and actuator_type either as a argument or as a key in the "
                "updated info"
            )
        actuator_status = await cls.get(
            session, ecosystem_uid=ecosystem_uid, actuator_type=actuator_type)
        if not actuator_status:
            values["ecosystem_uid"] = ecosystem_uid
            values["actuator_type"] = actuator_type
            await cls.create(session, values)
        elif values:
            await cls.update(session, values, ecosystem_uid, actuator_type)

    @classmethod
    async def get(
            cls,
            session: AsyncSession,
            ecosystem_uid: str,
            actuator_type: str,
    ) -> Self | None:
        stmt = (
            select(cls)
            .where(cls.ecosystem_uid == ecosystem_uid)
            .where(cls.actuator_type == actuator_type)
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @classmethod
    async def get_multiple(
            cls,
            session: AsyncSession,
            ecosystem_uids: list | None = None,
            actuator_types: list | None = None,
    ) -> Sequence[Self]:
        stmt = select(cls)
        if ecosystem_uids:
            stmt = stmt.where(cls.ecosystem_uid.in_(ecosystem_uids))
        if actuator_types:
            stmt = stmt.where(cls.actuator_type.in_(actuator_types))
        result = await session.execute(stmt)
        return result.scalars().all()


class Place(GaiaBase):
    __tablename__ = "places"

    id: Mapped[int] = mapped_column(primary_key=True)
    engine_uid: Mapped[UUID] = mapped_column(sa.ForeignKey("engines.uid"))
    name: Mapped[str] = mapped_column(sa.String(length=32))
    longitude: Mapped[float] = mapped_column()
    latitude: Mapped[float] = mapped_column()

    # relationships
    lightings: Mapped[list[Lighting]] = relationship(back_populates="target")
    engine: Mapped["Engine"] = relationship(back_populates="places")

    def __repr__(self) -> str:
        return (
            f"<Place({self.name}, coordinates=({self.longitude}, {self.latitude}))>"
        )

    @classmethod
    async def update(
            cls,
            session: AsyncSession,
            values: dict,
            engine_uid: str | None = None,
            name: str | None = None,
    ) -> None:
        engine_uid = engine_uid or values.pop("uid", None)
        if not engine_uid:
            raise ValueError(
                "Provide 'uid' either as a parameter or as a key in the updated info."
            )
        name = name or values.pop("uid", None)
        if not name:
            raise ValueError(
                "Provide 'name' either as a parameter or as a key in the updated info."
            )
        stmt = (
            update(cls)
            .where(
                cls.engine_uid == engine_uid,
                cls.name == name,
            )
            .values(**values)
        )
        await session.execute(stmt)

    @classmethod
    async def delete(
            cls,
            session: AsyncSession,
            engine_uid: str,
            name: str,
    ) -> None:
        stmt = (
            delete(cls)
            .where(
                cls.engine_uid == engine_uid,
                cls.name == name,
            )
        )
        await session.execute(stmt)

    @classmethod
    async def update_or_create(
            cls,
            session: AsyncSession,
            values: dict,
            engine_uid: str | None = None,
            name: str | None = None,
    ) -> None:
        engine_uid = engine_uid or values.pop("uid", None)
        if not engine_uid:
            raise ValueError(
                "Provide 'uid' either as a parameter or as a key in the updated info."
            )
        name = name or values.pop("uid", None)
        if not name:
            raise ValueError(
                "Provide 'name' either as a parameter or as a key in the updated info."
            )
        obj = await cls.get(session, engine_uid, name)
        if not obj:
            values["engine_uid"] = engine_uid
            values["name"] = name
            await cls.create(session, values)
        elif values:
            await cls.update(session, values, engine_uid, name)
        else:
            raise ValueError

    @classmethod
    async def get(
            cls,
            session: AsyncSession,
            engine_uid: str,
            name: str,
    ) -> Self | None:
        stmt = (
            select(cls)
            .where(
                cls.engine_uid == engine_uid,
                cls.name == name,
            )
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @classmethod
    async def get_multiple(
            cls,
            session: AsyncSession,
            engine_uid: list[str] | None = None,
            name: list[str] | None = None,
    ) -> Sequence[Self]:
        stmt = select(cls)
        if engine_uid:
            stmt = stmt.where(cls.ecosystem_uid.in_(engine_uid))
        if name:
            stmt = stmt.where(cls.ecosystem_uid.in_(name))
        result = await session.execute(stmt)
        return result.scalars().all()


class Lighting(GaiaBase):
    __tablename__ = "lightings"

    ecosystem_uid: Mapped[str] = mapped_column(sa.ForeignKey("ecosystems.uid"), primary_key=True)
    method: Mapped[gv.LightMethod] = mapped_column(default=gv.LightMethod.fixed)
    morning_start: Mapped[Optional[time]] = mapped_column()
    morning_end: Mapped[Optional[time]] = mapped_column()
    evening_start: Mapped[Optional[time]] = mapped_column()
    evening_end: Mapped[Optional[time]] = mapped_column()
    target_id: Mapped[Optional[int]] = mapped_column(sa.ForeignKey("places.id"))

    # relationships
    ecosystem: Mapped["Ecosystem"] = relationship(back_populates="lighting")
    target: Mapped[Optional["Place"]] = relationship(back_populates="lightings")

    def __repr__(self) -> str:
        return (
            f"<Lighting({self.ecosystem_uid}, status={self.status}, "
            f"mode={self.mode})>"
        )

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
        return result.scalar_one_or_none()

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
    ) -> None:
        ecosystem_uid = ecosystem_uid or values.pop("ecosystem_uid", None)
        if not ecosystem_uid:
            raise ValueError(
                "Provide ecosystem_uid either as an argument or as a key in the values"
            )
        obj = await cls.get(session, ecosystem_uid)
        if not obj:
            values["ecosystem_uid"] = ecosystem_uid
            await cls.create(session, values)
        elif values:
            await cls.update(session, values, ecosystem_uid)
        else:
            raise ValueError


class EnvironmentParameter(GaiaBase):
    __tablename__ = "environment_parameters"

    id: Mapped[int] = mapped_column(primary_key=True)
    ecosystem_uid: Mapped[str] = mapped_column(sa.String(length=8), sa.ForeignKey("ecosystems.uid"))
    parameter: Mapped[gv.ClimateParameter] = mapped_column()
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
            update(cls)
            .where(
                cls.ecosystem_uid == uid,
                cls.parameter == parameter
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
            delete(cls)
            .where(
                cls.ecosystem_uid == uid,
                cls.parameter == parameter
            )
        )
        await session.execute(stmt)

    @classmethod
    async def update_or_create(
            cls,
            session: AsyncSession,
            values: dict,
            uid: str | None = None,
            parameter: str | None = None,
    ) -> None:
        uid = uid or values.pop("uid", None)
        parameter = parameter or values.pop("parameter", None)
        if not (uid and parameter):
            raise ValueError(
                "Provide uid and parameter either as a argument or as a key in the "
                "updated info"
            )
        environment_parameter = await cls.get(
            session, uid=uid, parameter=parameter)
        if not environment_parameter:
            values["ecosystem_uid"] = uid
            values["parameter"] = parameter
            await cls.create(session, values)
        elif values:
            await cls.update(session, values, uid, parameter)
        else:
            raise ValueError

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
              sa.String(length=16),
              sa.ForeignKey("hardware.uid")),
    sa.Column("measure_id",
              sa.Integer,
              sa.ForeignKey("measures.id")),
)


AssociationActuatorPlant = Table(
    "association_actuators_plants", Base.metadata,
    sa.Column("sensor_uid",
              sa.String(length=16),
              sa.ForeignKey("hardware.uid")),
    sa.Column("plant_uid",
              sa.String(length=16),
              sa.ForeignKey("plants.uid")),
)


class Hardware(InConfigMixin, GaiaBase):
    __tablename__ = "hardware"

    uid: Mapped[str] = mapped_column(sa.String(length=16), primary_key=True)
    ecosystem_uid: Mapped[str] = mapped_column(
        sa.String(length=8), sa.ForeignKey("ecosystems.uid"), primary_key=True)
    name: Mapped[str] = mapped_column(sa.String(length=32))
    level: Mapped[gv.HardwareLevel] = mapped_column()
    address: Mapped[str] = mapped_column(sa.String(length=32))
    type: Mapped[gv.HardwareType] = mapped_column()
    model: Mapped[str] = mapped_column(sa.String(length=32))
    last_log: Mapped[Optional[datetime]] = mapped_column()

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

    async def attach_plants(
            self,
            session: AsyncSession,
            plants: list | str,
    ) -> None:
        if isinstance(plants, str):
            plants = [plants]
        self.plants.clear()
        plants = await Plant.get_multiple(session, plants_id=plants)
        for plant in plants:
            self.plants.append(plant)

    async def attach_measures(
            self,
            session: AsyncSession,
            measures: list[gv.Measure | gv.MeasureDict],
    ) -> None:
        self.measures.clear()
        for m in measures:
            if hasattr(m, "model_dump"):
                m = m.model_dump()
            m: gv.MeasureDict
            measure = await Measure.get(session, m["name"], m["unit"])
            if measure is None:
                await Measure.create(session, {"name": m["name"], "unit": m["unit"]})
                measure = await Measure.get(session, m["name"], m["unit"])
            self.measures.append(measure)

    @classmethod
    async def create(
            cls,
            session: AsyncSession,
            values: gv.HardwareConfigDict,
    ) -> None:
        measures: list[gv.Measure | gv.MeasureDict] = values.pop("measures", [])
        plants = values.pop("plants", [])
        stmt = insert(cls).values(values)
        await session.execute(stmt)
        if any((measures, plants)):
            hardware_obj = await cls.get(session, values["uid"])
            if measures:
                await hardware_obj.attach_measures(session, measures)
            if plants:
                await hardware_obj.attach_plants(session, plants)
            await session.commit()

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
            if measures:
                await hardware_obj.attach_measures(session, measures)
            if plants:
                await hardware_obj.attach_plants(session, plants)
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
            level: gv.HardwareLevel | list[gv.HardwareLevel] | None = None,
            type: gv.HardwareType | list[gv.HardwareType] | None = None,
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
            levels: gv.HardwareLevel | list[gv.HardwareLevel] | None = None,
            types: gv.HardwareType | list[gv.HardwareType] | None = None,
            models: str | list | None = None,
            in_config: bool | None = None,
    ) -> Sequence[Hardware]:
        stmt = cls.generate_query(
            hardware_uids, ecosystem_uids, levels, types, models
        )
        if in_config is not None:
            stmt = stmt.where(cls.in_config == in_config)
        result = await session.execute(stmt)
        return result.unique().scalars().all()

    @staticmethod
    def get_models_available() -> list:
        # TODO based on gaia / gaia-validators
        return []


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
            if hardware.type != gv.HardwareType.sensor:
                hardware = None
        return hardware

    @classmethod
    async def get_multiple(
            cls,
            session: AsyncSession,
            hardware_uids: str | list | None = None,
            ecosystem_uids: str | list | None = None,
            levels: gv.HardwareLevel | list[gv.HardwareLevel] | None = None,
            models: str | list | None = None,
            time_window: timeWindow = None,
            in_config: bool | None = None,
    ) -> Sequence[Self]:
        stmt = cls.generate_query(
            hardware_uids, ecosystem_uids, levels, gv.HardwareType.sensor, models)
        if time_window:
            stmt = cls._add_time_window_to_stmt(stmt, time_window)
        if in_config is not None:
            stmt = stmt.where(cls.in_config == in_config)
        result = await session.execute(stmt)
        return result.unique().scalars().all()

    async def get_current_data(
            self,
            session: AsyncSession,
            measures: str | list | None = None,
    ) -> list:
        measures_obj: list[Measure]
        if measures is None:
            measures_obj = self.measures
        else:
            if isinstance(measures, str):
                measures = measures.split(",")
            measures_obj = [
                measure for measure in self.measures
                if measure.name in measures
            ]
        rv = []
        for measure_obj in measures_obj:
            rv.append({
                "measure": measure_obj.name,
                "unit": measure_obj.unit,
                "values": await SensorDbCache.get_recent_timed_values(
                    session, self.uid, measure_obj.name),
            })
        return rv

    async def get_historic_data(
            self,
            session: AsyncSession,
            measures: str | list | None = None,
            time_window: timeWindow | None = None,
    ) -> list:
        measures_obj: list[Measure]
        if measures is None:
            measures_obj = self.measures
        else:
            if isinstance(measures, str):
                measures = measures.split(",")
            measures_obj = [
                measure for measure in self.measures
                if measure.name in measures
            ]
        if time_window is None:
            time_window = create_time_window()
        rv = []
        for measure_obj in measures_obj:
            rv.append({
                "measure": measure_obj.name,
                "unit": measure_obj.unit,
                "span": (time_window.start, time_window.end),
                "values": await SensorRecord.get_timed_values(
                    session, self.uid, measure_obj.name, time_window),
            })
        return rv

    async def get_overview(
            self,
            session: AsyncSession,
            measures: str | list | None = None,
            current_data: bool = False,
            historic_data: bool = False,
            time_window: timeWindow | None = None,
    ) -> dict:
        rv = self.to_dict()
        rv["data"] = None
        if current_data or historic_data:
            rv.update({"data": {}})
            if current_data:
                rv["data"].update({
                    "current": await self.get_current_data(session, measures)
                })
            else:
                rv["data"].update({"current": None})
            if historic_data:
                if time_window is None:
                    time_window = create_time_window()
                rv["data"].update({
                    "historic": await self.get_historic_data(
                        session, measures, time_window)
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
            if hardware.type == gv.HardwareType.sensor:
                hardware = None
        return hardware

    @classmethod
    async def get_multiple(
            cls,
            session: AsyncSession,
            hardware_uids: str | list | None = None,
            ecosystem_uids: str | list | None = None,
            type: gv.HardwareType | list[gv.HardwareType] | None = None,
            levels: gv.HardwareLevel | list[gv.HardwareLevel] | None = None,
            models: str | list | None = None,
            time_window: timeWindow = None,
            in_config: bool | None = None,
    ) -> Sequence[Self]:
        if type is not None:
            if isinstance(type, list):
                for t in type:
                    assert t in gv.HardwareType.actuator
            else:
                assert type in gv.HardwareType.actuator
        stmt = cls.generate_query(
            hardware_uids, ecosystem_uids, levels, type, models)
        if time_window:
            stmt = cls._add_time_window_to_stmt(stmt, time_window)
        if in_config is not None:
            stmt = stmt.where(cls.in_config == in_config)
        result = await session.execute(stmt)
        hardware: Sequence[Hardware] = result.unique().scalars().all()
        return [h for h in hardware if h.type != gv.HardwareType.sensor]


class Measure(GaiaBase):
    __tablename__ = "measures"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(sa.String(length=32))
    unit: Mapped[Optional[str]] = mapped_column(sa.String(length=32))

    # relationships
    hardware: Mapped[list["Hardware"]] = relationship(
        back_populates="measures", secondary=AssociationHardwareMeasure)

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
            name: str,
            unit: str | None = None,
    ) -> Self | None:
        stmt = select(cls).where(
            (cls.name == name)
            & (cls.unit == unit)
        )
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


class Plant(InConfigMixin, GaiaBase):
    __tablename__ = "plants"

    uid: Mapped[str] = mapped_column(sa.String(length=16), primary_key=True)
    name: Mapped[str] = mapped_column(sa.String(length=32))
    ecosystem_uid: Mapped[str] = mapped_column(sa.ForeignKey("ecosystems.uid"))
    species: Mapped[Optional[int]] = mapped_column(sa.String(length=32), index=True)
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
            plants_id: list[str] | None = None,
            in_config: bool | None = None,
    ) -> Sequence[Self]:
        stmt = select(cls)
        if plants_id:
            stmt = stmt.where(
                (cls.name.in_(plants_id))
                | (cls.uid.in_(plants_id))
            )
        if in_config is not None:
            stmt = stmt.where(cls.in_config == in_config)
        result = await session.execute(stmt)
        return result.scalars().all()


class SensorRecord(BaseSensorRecord):
    __tablename__ = "sensor_records"
    __archive_link__ = ArchiveLink("sensor", "recent")

    # relationships
    ecosystem: Mapped["Ecosystem"] = relationship(back_populates="sensor_records")
    sensor: Mapped["Hardware"] = relationship(back_populates="sensor_records")

    @classmethod
    async def get_records(
            cls,
            session: AsyncSession,
            sensor_uid: str,
            measure_name: str,
            time_window: timeWindow
    ) -> Sequence[Self]:
        return await super().get_records(
            session, sensor_uid, measure_name, time_window)

    @classmethod
    @cached(_cache_sensor_values, key=sessionless_hashkey)
    async def get_timed_values(
            cls,
            session: AsyncSession,
            sensor_uid: str,
            measure_name: str,
            time_window: timeWindow
    ) -> list[tuple[datetime, float]]:
        stmt = (
            select(cls.timestamp, cls.value)
            .where(cls.measure == measure_name)
            .where(cls.sensor_uid == sensor_uid)
            .where(
                (cls.timestamp > time_window.start)
                & (cls.timestamp <= time_window.end)
            )
        )
        result = await session.execute(stmt)
        return [r._data for r in result.all()]


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

    @classmethod
    async def get_records(
            cls,
            session: AsyncSession,
            ecosystem_uid: str,
            time_window: timeWindow,
    ) -> Sequence[Self]:
        stmt = (
            select(cls)
            .where(cls.ecosystem_uid == ecosystem_uid)
            .where(
                (cls.timestamp > time_window.start)
                & (cls.timestamp <= time_window.end)
            )
        )
        result = await session.execute(stmt)
        return result.scalars().all()


class GaiaWarning(Base):
    __tablename__ = "warnings"
    __archive_link__ = ArchiveLink("warnings", "recent")

    id: Mapped[int] = mapped_column(primary_key=True)
    level: Mapped[ImportanceLevel] = mapped_column(default=ImportanceLevel.low)
    title: Mapped[str] = mapped_column(sa.String(length=256))
    description: Mapped[Optional[str]] = mapped_column(sa.String(length=2048))
    created_on: Mapped[datetime] = mapped_column(UtcDateTime, default=func.current_timestamp())
    created_by: Mapped[str] = mapped_column(sa.ForeignKey("ecosystems.uid"))
    updated_on: Mapped[Optional[datetime]] = mapped_column(UtcDateTime)
    seen_on: Mapped[Optional[datetime]] = mapped_column(UtcDateTime)
    seen_by: Mapped[Optional[int]] = mapped_column()
    solved_on: Mapped[Optional[datetime]] = mapped_column(UtcDateTime)
    solved_by: Mapped[Optional[int]] = mapped_column()

    @property
    def seen(self):
        return self.seen_on is not None

    @property
    def solved(self):
        return self.solved_on is not None

    @classmethod
    async def create(
            cls,
            session: AsyncSession,
            ecosystem_uid: str,
            values: dict,
    ) -> None:
        values["created_by"] = ecosystem_uid
        stmt = insert(cls).values(values)
        await session.execute(stmt)

    @classmethod
    @cached(_cache_warnings, key=sessionless_hashkey)
    async def get_multiple(
            cls,
            session: AsyncSession,
            limit: int = 10,
            show_solved: bool = False,
    ) -> Sequence[Self]:
        stmt = (
            select(cls)
            .order_by(cls.created_on.desc())
            .limit(limit)
        )
        if not show_solved:
            stmt = stmt.where(cls.solved_on == None)
        result = await session.execute(stmt)
        return result.scalars().all()

    @classmethod
    async def update(
            cls,
            session: AsyncSession,
            warning_id: int,
            ecosystem_uid: str,
            values: dict,
    ) -> None:
        values.pop("seen_on", None)
        values.pop("solved_on", None)
        stmt = (
            update(cls)
            .where(
                (cls.id == warning_id)
                & (cls.created_by == ecosystem_uid)
            )
            .values(**values)
        )
        await session.execute(stmt)
        _cache_warnings.clear()

    @classmethod
    async def mark_as_seen(
            cls,
            session: AsyncSession,
            warning_id: int,
            user_id: int,
    ) -> None:
        stmt = (
            update(cls)
            .where(
                (cls.id == warning_id)
                & (cls.seen_on == None)  # Make sure we don't mark twice
            )
            .values({
                "seen_on": datetime.now(timezone.utc),
                "seen_by": user_id,
            })
        )
        await session.execute(stmt)
        _cache_warnings.clear()

    @classmethod
    async def mark_as_solved(
            cls,
            session: AsyncSession,
            warning_id: int,
            user_id: int,
    ) -> None:
        stmt = (
            update(cls)
            .where(
                (cls.id == warning_id)
                & (cls.solved_on == None)  # Make sure we don't mark twice
            )
            .values({
                "solved_on": datetime.now(timezone.utc),
                "solved_by": user_id,
            })
        )
        await session.execute(stmt)
        await cls.mark_as_seen(session, warning_id=warning_id, user_id=user_id)
        _cache_warnings.clear()


class CrudRequest(GaiaBase):
    __tablename__ = "crud_requests"

    uuid: Mapped[UUID] = mapped_column(primary_key=True)
    engine_uid: Mapped[str] = mapped_column(sa.ForeignKey("engines.uid"))
    ecosystem_uid: Mapped[str] = mapped_column(sa.ForeignKey("ecosystems.uid"))
    created_on: Mapped[datetime] = mapped_column(UtcDateTime, default=func.current_timestamp())
    result: Mapped[Optional[gv.Result]] = mapped_column()
    action: Mapped[gv.CrudAction] = mapped_column()
    target: Mapped[str] = mapped_column(sa.String(length=32))
    payload: Mapped[Optional[str]] = mapped_column(sa.String(length=1024))
    message: Mapped[Optional[str]] = mapped_column(sa.String(length=256))

    @property
    def completed(self) -> bool:
        return self.result is not None

    @classmethod
    async def get(cls, session: AsyncSession, uuid: UUID) -> Self | None:
        stmt = select(cls).where(cls.uuid == uuid)
        result = await session.execute(stmt)
        return result.scalars().one_or_none()

    @classmethod
    async def get_multiple(
            cls,
            session: AsyncSession,
            uuid: list[UUID] | None = None,
            limit: int = 15,
    ) -> Sequence[Self]:
        stmt = select(cls)
        if uuid is not None:
            stmt = stmt.where(cls.uuid.in_(uuid))
        stmt = (
            stmt
            .order_by(cls.created_on.desc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        return result.scalars().all()

    @classmethod
    async def get_for_engine(
            cls,
            session: AsyncSession,
            engine_uid: str,
            limit: int = 10,
    ) -> Sequence[Self]:
        stmt = (
            select(cls)
            .where(cls.engine_uid == engine_uid)
            .limit(limit)
        )
        result = await session.execute(stmt)
        return result.scalars().all()
