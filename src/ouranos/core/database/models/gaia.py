from __future__ import annotations

from abc import abstractmethod
from datetime import datetime, time, timedelta, timezone
from typing import Optional, Sequence, Self, TypedDict
from uuid import UUID

from asyncache import cached
from cachetools import LRUCache, TTLCache
from dispatcher import AsyncDispatcher
import sqlalchemy as sa
from sqlalchemy import delete, insert, select, UniqueConstraint, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.declarative import declared_attr
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.schema import Table
from sqlalchemy.sql import func
from sqlalchemy.sql.functions import max as sa_max

import gaia_validators as gv

from ouranos import current_app
from ouranos.core.database.models.abc import (
    Base, CacheMixin, CRUDMixin, RecordMixin)
from ouranos.core.database.models.types import UtcDateTime
from ouranos.core.database.models.utils import sessionless_hashkey, TIME_LIMITS
from ouranos.core.database.utils import ArchiveLink
from ouranos.core.utils import create_time_window, timeWindow


RecentOrConnected = Literal["recent", "connected", "all"]

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


class EcosystemActuatorTypesManagedDict(TypedDict):
    light: bool
    cooler: bool
    heater: bool
    humidifier: bool
    dehumidifier: bool


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
class Engine(Base, CRUDMixin):
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
    async def get_by_id(
            cls,
            session: AsyncSession,
            /,
            engine_id: str | UUID,
    ) -> Self | None:
        if isinstance(engine_id, UUID):
            # Received an engine sid
            stmt = select(cls).where(cls.sid == engine_id)
        else:
            # Received an engine uid
            stmt = select(cls).where(cls.uid == engine_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @classmethod
    async def get_multiple_by_id(
            cls,
            session: AsyncSession,
            /,
            engines_id: RecentOrConnected | list[str] | list[UUID] | None = None,
    ) -> Sequence[Self]:
        if engines_id is None or engines_id == "all":
            stmt = (
                select(cls)
                .order_by(cls.last_seen.desc())
            )
            result = await session.execute(stmt)
            return result.scalars().all()
        elif engines_id == "recent":
            time_limit = datetime.now(timezone.utc) - timedelta(hours=TIME_LIMITS.RECENT)
            stmt = (
                select(cls)
                .where(cls.last_seen >= time_limit)
                .order_by(cls.last_seen.desc())
            )
            result = await session.execute(stmt)
            return result.scalars().all()
        elif engines_id == "connected":
            stmt = (
                select(cls)
                .where(cls.connected == True)  # noqa
                .order_by(cls.uid.asc())
            )
            result = await session.execute(stmt)
            return result.scalars().all()
        if isinstance(engines_id, str):
            # Should not happen
            engines_id = engines_id.split(",")
        # Check that all the list elements are of the same types as it can lead
        #  to issues on some backend
        lst_type = type(engines_id[0])
        if len(engines_id) > 0:
            if not all(isinstance(id_, lst_type) for id_ in engines_id[1:]):
                raise ValueError(
                    "All the elements should either be engines 'uid' or 'name'"
                )
        if lst_type == str:
            # Received an engine uid
            stmt = select(cls).where(cls.uid.in_(engines_id))
        else:
            # Received an engine sid
            # Received an engine sid
            stmt = select(cls).where(cls.sid.in_(engines_id))
        stmt = stmt.order_by(cls.uid.asc())
        result = await session.execute(stmt)
        return result.scalars().all()

    async def get_crud_requests(self, session: AsyncSession) -> Sequence[CrudRequest]:
        response = await CrudRequest.get_for_engine(session, self.uid)
        return response


class Ecosystem(Base, CRUDMixin, InConfigMixin):
    __tablename__ = "ecosystems"

    uid: Mapped[str] = mapped_column(sa.String(length=8), primary_key=True)
    engine_uid: Mapped[str] = mapped_column(sa.String(length=32), sa.ForeignKey("engines.uid"))
    name: Mapped[str] = mapped_column(sa.String(length=32), default="_registering")
    status: Mapped[bool] = mapped_column(default=False)
    registration_date: Mapped[datetime] = mapped_column(UtcDateTime, default=func.current_timestamp())
    last_seen: Mapped[datetime] = mapped_column(UtcDateTime, default=func.current_timestamp())  # , onupdate=func.current_timestamp())
    management: Mapped[int] = mapped_column(default=0)
    day_start: Mapped[time] = mapped_column(default=time(8, 00))
    night_start: Mapped[time] = mapped_column(default=time(20, 00))

    # relationships
    engine: Mapped["Engine"] = relationship(back_populates="ecosystems", lazy="selectin")
    lighting: Mapped["Lighting"] = relationship(back_populates="ecosystem", uselist=False, lazy="selectin")
    environment_parameters: Mapped[list["EnvironmentParameter"]] = relationship(back_populates="ecosystem")
    plants: Mapped[list["Plant"]] = relationship(back_populates="ecosystem")
    hardware: Mapped[list["Hardware"]] = relationship(back_populates="ecosystem")
    sensor_records: Mapped[list["SensorDataRecord"]] = relationship(back_populates="ecosystem")
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
    def lighting_method(self) -> gv.LightingMethod | None:
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
    ) -> Sequence[Self]:
        if ecosystems is None:
            stmt = (
                select(cls)
                .order_by(cls.name.asc(),
                          cls.last_seen.desc())
            )
            if in_config is not None:
                stmt = stmt.where(cls.in_config == in_config)
            result = await session.execute(stmt)
            return result.scalars().all()

        if isinstance(ecosystems, str):
            ecosystems = ecosystems.split(",")
        if "recent" in ecosystems:
            time_limit = datetime.now(timezone.utc) - timedelta(hours=TIME_LIMITS.RECENT)
            stmt = (
                select(cls)
                .where(cls.last_seen >= time_limit)
                .order_by(cls.status.desc(), cls.name.asc())
            )
        elif "connected" in ecosystems:
            stmt = (
                select(cls).join(Engine.ecosystems)
                .where(Engine.connected == True)  # noqa
                .order_by(cls.name.asc())
            )
        else:
            stmt = (
                select(cls)
                .where(cls.uid.in_(ecosystems) |
                       cls.name.in_(ecosystems))
                .order_by(cls.last_seen.desc(), cls.name.asc())
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
            *,
            level: gv.HardwareLevel,
    ) -> bool:
        time_limit = datetime.now(timezone.utc) - timedelta(hours=TIME_LIMITS.SENSORS)
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

    async def get_functionalities(self, session: AsyncSession) -> dict:
        return {
            "uid": self.uid,
            "name": self.name,
            **self.management_dict,
            "switches": any((
                self.management_dict.get("climate"),
                self.management_dict.get("light")
            )),
            "environment_data": await self.has_recent_sensor_data(
                session, level=gv.HardwareLevel.environment),
            "plants_data": await self.has_recent_sensor_data(
                session, level=gv.HardwareLevel.plants),
        }

    async def get_hardware(
            self,
            session: AsyncSession,
            hardware_type: gv.HardwareType | None = None,
            in_config: bool | None = None,
    ) -> Sequence[Hardware]:
        return await Hardware.get_multiple(
            session, ecosystem_uids=[self.uid], types=hardware_type,
            in_config=in_config)

    @cached(_cache_sensors_data_skeleton, key=sessionless_hashkey)
    async def get_sensors_data_skeleton(
            self,
            session: AsyncSession,
            *,
            time_window: timeWindow,
            level: gv.HardwareLevel | list[gv.HardwareLevel] | None = None,
    ) -> dict:
        stmt = (
            select(Hardware).join(SensorDataRecord.sensor)
            .where(Hardware.ecosystem_uid == self.uid)
            .where(
                (SensorDataRecord.timestamp > time_window.start)
                & (SensorDataRecord.timestamp <= time_window.end)
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
            "span": (time_window.start, time_window.end),
            "sensors_skeleton": skeleton,
        }

    async def get_current_data(self, session: AsyncSession) -> Sequence[SensorDataCache]:
        return await SensorDataCache.get_recent(session, self.uid)

    async def get_actuators_state(
            self,
            session: AsyncSession
    ) -> list[ActuatorState]:
        stmt = (
            select(ActuatorState)
            .where(ActuatorState.ecosystem_uid == self.uid)
        )
        result = await session.execute(stmt)
        actuators_status = result.scalars().all()
        return actuators_status

    async def get_timed_values(
            self,
            session: AsyncSession,
            actuator_type: gv.HardwareType,
            time_window: timeWindow,
    ) -> list[tuple[datetime, bool, gv.ActuatorMode, bool, float | None]]:
        return await ActuatorRecord.get_timed_values(
            session, ecosystem_uid=self.uid, actuator_type=actuator_type,
            time_window=time_window)

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


class ActuatorState(Base, CRUDMixin):
    __tablename__ = "actuator_states"

    ecosystem_uid: Mapped[str] = mapped_column(sa.ForeignKey("ecosystems.uid"), primary_key=True)
    type: Mapped[gv.HardwareType] = mapped_column(primary_key=True)
    active: Mapped[bool] = mapped_column(default=False)
    mode: Mapped[gv.ActuatorMode] = mapped_column(default=gv.ActuatorMode.automatic)
    status: Mapped[bool] = mapped_column(default=False)
    level: Mapped[Optional[float]] = mapped_column(sa.Float(precision=2), default=None)

    @classmethod
    async def update(
            cls,
            session: AsyncSession,
            actuator_info: dict,
            ecosystem_uid: str | None = None,
            actuator_type: gv.HardwareType | None = None,
    ) -> None:
        ecosystem_uid = ecosystem_uid or actuator_info.pop("ecosystem_uid", None)
        actuator_type = actuator_type or actuator_info.pop("type", None)
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
                cls.type == actuator_type
            )
            .values(**actuator_info)
        )
        await session.execute(stmt)

    @classmethod
    async def delete(
            cls,
            session: AsyncSession,
            ecosystem_uid: str,
            actuator_type: gv.HardwareType,
    ) -> None:
        stmt = (
            delete(cls)
            .where(
                cls.ecosystem_uid == ecosystem_uid,
                cls.type == actuator_type,
            )
        )
        await session.execute(stmt)

    @classmethod
    async def update_or_create(
            cls,
            session: AsyncSession,
            values: dict,
            ecosystem_uid: str | None = None,
            actuator_type: gv.HardwareType | None = None,
    ) -> None:
        ecosystem_uid = ecosystem_uid or values.pop("ecosystem_uid", None)
        actuator_type = actuator_type or values.pop("type", None)
        if not (ecosystem_uid and actuator_type):
            raise ValueError(
                "Provide uid and actuator_type either as a argument or as a key in the "
                "updated info"
            )
        actuator_status = await cls.get(
            session, ecosystem_uid=ecosystem_uid, actuator_type=actuator_type)
        if not actuator_status:
            values["ecosystem_uid"] = ecosystem_uid
            values["type"] = actuator_type
            await cls.create(session, values)
        elif values:
            await cls.update(session, values, ecosystem_uid, actuator_type)

    @classmethod
    async def get(
            cls,
            session: AsyncSession,
            ecosystem_uid: str,
            actuator_type: gv.HardwareType,
    ) -> Self | None:
        stmt = (
            select(cls)
            .where(cls.ecosystem_uid == ecosystem_uid)
            .where(cls.type == actuator_type)
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @classmethod
    async def get_multiple(
            cls,
            session: AsyncSession,
            ecosystem_uids: list[str] | None = None,
            actuator_types: list[gv.HardwareType] | None = None,
    ) -> Sequence[Self]:
        stmt = select(cls)
        if ecosystem_uids:
            stmt = stmt.where(cls.ecosystem_uid.in_(ecosystem_uids))
        if actuator_types:
            stmt = stmt.where(cls.type.in_(actuator_types))
        result = await session.execute(stmt)
        return result.scalars().all()


class Place(Base, CRUDMixin):
    __tablename__ = "places"
    __table_args__ = (
        UniqueConstraint(
            "engine_uid", "name",
            name="uq_places_engine_uid"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)  # Use this as PK as it eases linking with Lighting
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
        engine_uid = engine_uid or values.pop("engine_uid", None)
        if not engine_uid:
            raise ValueError(
                "Provide 'uid' either as a parameter or as a key in the updated info."
            )
        name = name or values.pop("name", None)
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


class Lighting(Base, CRUDMixin):
    __tablename__ = "lightings"

    ecosystem_uid: Mapped[str] = mapped_column(sa.ForeignKey("ecosystems.uid"), primary_key=True)
    method: Mapped[gv.LightingMethod] = mapped_column(default=gv.LightingMethod.fixed)
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
            values: dict,
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


class EnvironmentParameter(Base, CRUDMixin):
    __tablename__ = "environment_parameters"

    ecosystem_uid: Mapped[str] = mapped_column(
        sa.String(length=8), sa.ForeignKey("ecosystems.uid"), primary_key=True)
    parameter: Mapped[gv.ClimateParameter] = mapped_column(primary_key=True)
    day: Mapped[float] = mapped_column(sa.Float(precision=2))
    night: Mapped[float] = mapped_column(sa.Float(precision=2))
    hysteresis: Mapped[float] = mapped_column(sa.Float(precision=2), default=0.0)
    alarm: Mapped[Optional[float]] = mapped_column(sa.Float(precision=2), default=None)

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


class Hardware(Base, CRUDMixin, InConfigMixin):
    __tablename__ = "hardware"

    uid: Mapped[str] = mapped_column(sa.String(length=16), primary_key=True)
    ecosystem_uid: Mapped[str] = mapped_column(
        sa.String(length=8), sa.ForeignKey("ecosystems.uid"))
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
    sensor_records: Mapped[list["SensorDataRecord"]] = relationship(
        back_populates="sensor")

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
    ) -> Self | None:
        stmt = select(cls).where(cls.uid == hardware_uid)
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
    ) -> Sequence[Self]:
        stmt = cls.generate_query(
            hardware_uids, ecosystem_uids, levels, types, models
        )
        if in_config is not None:
            stmt = stmt.where(cls.in_config == in_config)
        result = await session.execute(stmt)
        return result.unique().scalars().all()

    @staticmethod
    def get_models_available() -> list[str]:
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
            stmt.join(SensorDataRecord.sensor)
            .where(
                (SensorDataRecord.timestamp > time_window.start) &
                (SensorDataRecord.timestamp <= time_window.end)
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
            measure: str,
    ) -> dict | None:
        measure_str = measure
        measure_obj: Measure | None = None
        for measure in self.measures:
            if measure.name == measure_str:
                measure_obj = measure
                break
        if measure_obj is None:
            return None
        return {
            "measure": measure_obj.name,
            "unit": measure_obj.unit,
            "values": await SensorDataCache.get_recent_timed_values(
                session, self.uid, measure_obj.name),
        }

    async def get_historic_data(
            self,
            session: AsyncSession,
            measure: str,
            time_window: timeWindow | None = None,
    ) -> dict | None:
        measure_str = measure
        measure_obj: Measure | None = None
        for measure in self.measures:
            if measure.name == measure_str:
                measure_obj = measure
                break
        if measure_obj is None:
            return None
        if time_window is None:
            time_window = create_time_window()
        return {
            "measure": measure_obj.name,
            "unit": measure_obj.unit,
            "span": (time_window.start, time_window.end),
            "values": await SensorDataRecord.get_timed_values(
                session, sensor_uid=self.uid, measure_name=measure_obj.name,
                time_window=time_window),
        }

    @staticmethod
    async def create_records(
            session: AsyncSession,
            values: dict | list[dict],
    ) -> None:
        await SensorDataRecord.create_records(session, values)


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


class Measure(Base, CRUDMixin):
    __tablename__ = "measures"

    id: Mapped[int] = mapped_column(primary_key=True)  # Use this as PK as the name might be changed
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
            *,
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


class Plant(Base, CRUDMixin, InConfigMixin):
    __tablename__ = "plants"

    uid: Mapped[str] = mapped_column(sa.String(length=16), primary_key=True)
    ecosystem_uid: Mapped[str] = mapped_column(sa.ForeignKey("ecosystems.uid"))
    name: Mapped[str] = mapped_column(sa.String(length=32))
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


# ---------------------------------------------------------------------------
#   Sensors data
# ---------------------------------------------------------------------------
class BaseSensorData(Base):
    __abstract__ = True
    __table_args__ = (
        UniqueConstraint(
            "measure", "timestamp", "value", "ecosystem_uid", "sensor_uid",
            name="_no_repost_constraint"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(UtcDateTime)
    value: Mapped[float] = mapped_column(sa.Float(precision=2))

    @declared_attr
    def measure(cls) -> Mapped[str]:
        return mapped_column(
            sa.String(length=32), sa.ForeignKey("measures.name"), index=True
        )

    @declared_attr
    def ecosystem_uid(cls) -> Mapped[str]:
        return mapped_column(
            sa.String(length=8), sa.ForeignKey("ecosystems.uid"), index=True
        )

    @declared_attr
    def sensor_uid(cls) -> Mapped[str]:
        return mapped_column(
            sa.String(length=16), sa.ForeignKey("hardware.uid"), index=True
        )


class SensorDataCache(BaseSensorData, CacheMixin):
    __tablename__ = "sensor_temp"
    __bind_key__ = "memory"

    logged: Mapped[bool] = mapped_column(default=False)

    @classmethod
    def get_ttl(cls) -> int:
        return current_app.config["ECOSYSTEM_TIMEOUT"]

    @classmethod
    async def get_recent(
            cls,
            session: AsyncSession,
            ecosystem_uid: str | list | None = None,
            sensor_uid: str | list | None = None,
            measure: str | list | None = None,
            discard_logged: bool = False,
    ) -> Sequence[Self]:
        await cls.remove_expired(session)
        sub_stmt = (
            select(cls.id, sa_max(cls.timestamp))
            .group_by(cls.sensor_uid, cls.measure)
            .subquery()
        )
        stmt = select(cls).join(sub_stmt, cls.id == sub_stmt.c.id)

        local_vars = locals()
        args = "ecosystem_uid", "sensor_uid", "measure"
        for arg in args:
            value = local_vars.get(arg)
            if value:
                if isinstance(value, str):
                    value = value.split(",")
                hardware_attr = getattr(cls, arg)
                stmt = stmt.where(hardware_attr.in_(value))
        if discard_logged:
            stmt = stmt.where(cls.logged == False)
        result = await session.execute(stmt)
        return result.scalars().all()

    @classmethod
    async def get_recent_timed_values(
            cls,
            session: AsyncSession,
            sensor_uid: str,
            measure: str,
    ) -> list[tuple[datetime, float]]:
        await cls.remove_expired(session)
        sub_stmt = (
            select(cls.id, sa_max(cls.timestamp))
            .group_by(cls.sensor_uid, cls.measure)
            .subquery()
        )
        stmt = (
            select(cls.timestamp, cls.value)
            .join(sub_stmt, cls.id == sub_stmt.c.id)
            .where(cls.sensor_uid == sensor_uid)
            .where(cls.measure == measure)
        )
        result = await session.execute(stmt)
        return result.all()


class BaseSensorDataRecord(BaseSensorData, RecordMixin):
    __abstract__ = True

    @classmethod
    async def get_records(
            cls,
            session: AsyncSession,
            sensor_uid: str,
            measure_name: str,
            time_window: timeWindow
    ) -> Sequence[Self]:
        stmt = (
            select(cls)
            .where(cls.measure == measure_name)
            .where(cls.sensor_uid == sensor_uid)
            .where(
                (cls.timestamp > time_window.start)
                & (cls.timestamp <= time_window.end)
            )
        )
        result = await session.execute(stmt)
        return result.scalars().all()


class SensorDataRecord(BaseSensorDataRecord):
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
            *,
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
        return result.all()


# ---------------------------------------------------------------------------
#   Sensor alarms
# ---------------------------------------------------------------------------
class SensorAlarm(Base):
    __tablename__ = "sensor_alarms"

    id: Mapped[int] = mapped_column(primary_key=True)
    sensor_uid: Mapped[str] = mapped_column(sa.String(length=16), sa.ForeignKey("hardware.uid"))
    ecosystem_uid: Mapped[str] = mapped_column(sa.ForeignKey("ecosystems.uid"))
    measure: Mapped[str] = mapped_column(sa.String(length=32), sa.ForeignKey("measures.name"))
    position: Mapped[gv.Position] = mapped_column()
    delta: Mapped[float] = mapped_column()
    level: Mapped[gv.WarningLevel] = mapped_column()
    timestamp_from: Mapped[datetime] = mapped_column(UtcDateTime, default=func.current_timestamp())
    timestamp_to: Mapped[datetime] = mapped_column(UtcDateTime, default=func.current_timestamp(), onupdate=func.current_timestamp())
    timestamp_max: Mapped[datetime] = mapped_column(UtcDateTime, default=func.current_timestamp())
    seen_on: Mapped[Optional[datetime]] = mapped_column(UtcDateTime)
    seen_by: Mapped[Optional[int]] = mapped_column()

    @classmethod
    async def create(
            cls,
            session: AsyncSession,
            values: dict,
    ) -> Self:
        values = {**values}  # Don't mutate original values
        timestamp = values.pop("timestamp")
        alarm = cls(
            **values, timestamp_from=timestamp, timestamp_to=timestamp,
            timestamp_max=timestamp)
        session.add(alarm)
        return alarm

    @classmethod
    async def get(
            cls,
            session: AsyncSession,
            sensor_uid: str,
            measure: str,
            time_limit: timedelta,
    ) -> Self | None:
        time_limit = datetime.now(timezone.utc) - time_limit
        stmt = (
            select(cls)
            .where(
                (cls.sensor_uid == sensor_uid)
                & (cls.measure == measure)
                & (cls.timestamp_to > time_limit)
            )
            .order_by(cls.timestamp_to.desc())
        )
        result = await session.execute(stmt)
        return result.scalars().first()

    @classmethod
    async def get_multiple(
            cls,
            session: AsyncSession,
            ecosystem_uid: str | list[str] | None = None,
            sensor_uid: str | list[str] | None = None,
            measure: str | list[str] | None = None,
            time_limit: timedelta = timedelta(days=7),
    ) -> Sequence[Self]:
        time_limit = datetime.now(timezone.utc) - time_limit
        stmt = (
            select(cls)
            .where(cls.timestamp_to > time_limit)
        )
        if ecosystem_uid is not None:
            if isinstance(ecosystem_uid, str):
                ecosystem_uid = [ecosystem_uid, ]
                stmt = stmt.where(cls.ecosystem_uid.in_(ecosystem_uid))
        if sensor_uid is not None:
            if isinstance(sensor_uid, str):
                sensor_uid = [sensor_uid, ]
                stmt = stmt.where(cls.sensor_uid.in_(sensor_uid))
        if measure is not None:
            if isinstance(measure, str):
                measure = [measure, ]
                stmt = stmt.where(cls.measure.in_(measure))
        result = await session.execute(stmt)
        return result.scalars().all()

    @classmethod
    async def get_recent(
            cls,
            session: AsyncSession,
            sensor_uid: str,
            measure: str,
            time_limit: timedelta = timedelta(minutes=35),
    ) -> Self | None:
        return await cls.get(
            session, sensor_uid=sensor_uid, measure=measure, time_limit=time_limit)

    @classmethod
    async def create_or_lengthen(
            cls,
            session: AsyncSession,
            values: dict,
    ) -> None:
        alarm = await cls.get_recent(
            session, sensor_uid=values["sensor_uid"], measure=values["measure"])
        if alarm is None:
            alarm = await cls.create(session, values=values)
        else:
            # Update delta and level if it changes
            if values["delta"] > alarm.delta:
                alarm.delta = values["delta"]
                alarm.level = values["level"]
                alarm.timestamp_max = values["timestamp"]
        alarm.timestamp_to = values["timestamp"]

    @classmethod
    async def mark_as_seen(
            cls,
            session: AsyncSession,
            alarm_id: int,
            user_id: int,
    ) -> None:
        stmt = (
            update(cls)
            .where(
                (cls.id == alarm_id)
                & (cls.seen_on == None)  # Make sure we don't mark twice
            )
            .values({
                "seen_on": datetime.now(timezone.utc),
                "seen_by": user_id,
            })
        )
        await session.execute(stmt)


# ---------------------------------------------------------------------------
#   Actuators data
# ---------------------------------------------------------------------------
class BaseActuatorRecord(Base, RecordMixin):
    __abstract__ = True

    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[gv.HardwareType] = mapped_column()
    timestamp: Mapped[datetime] = mapped_column(UtcDateTime)
    active: Mapped[bool] = mapped_column(default=False)
    mode: Mapped[gv.ActuatorMode] = mapped_column(default=gv.ActuatorMode.automatic)
    status: Mapped[bool] = mapped_column(default=False)
    level: Mapped[Optional[float]] = mapped_column(sa.Float(precision=2), default=None)

    @declared_attr
    def ecosystem_uid(cls) -> Mapped[str]:
        return mapped_column(
            sa.String(length=8), sa.ForeignKey("ecosystems.uid"), index=True
        )

    @classmethod
    async def get_records(
            cls,
            session: AsyncSession,
            ecosystem_uid: str,
            actuator_type: gv.HardwareType,
            time_window: timeWindow,
    ) -> Sequence[Self]:
        stmt = (
            select(cls)
            .where(cls.ecosystem_uid == ecosystem_uid)
            .where(cls.type == actuator_type)
            .where(
                (cls.timestamp > time_window.start)
                & (cls.timestamp <= time_window.end)
            )
        )
        result = await session.execute(stmt)
        return result.scalars().all()

    @classmethod
    async def get_timed_values(
            cls,
            session: AsyncSession,
            ecosystem_uid: str,
            actuator_type: gv.HardwareType,
            time_window: timeWindow,
    ) -> list[tuple[datetime, bool, gv.ActuatorMode, bool, float | None]]:
        stmt = (
            select(cls.timestamp, cls.active, cls.mode, cls.status, cls.level)
            .where(cls.ecosystem_uid == ecosystem_uid)
            .where(cls.type == actuator_type)
            .where(
                (cls.timestamp > time_window.start)
                & (cls.timestamp <= time_window.end)
            )
        )
        result = await session.execute(stmt)
        return result.all()


class ActuatorRecord(BaseActuatorRecord):
    __tablename__ = "actuator_records"
    __archive_link__ = ArchiveLink("actuator", "recent")

    # relationships
    ecosystem: Mapped["Ecosystem"] = relationship(back_populates="actuator_records")


# ---------------------------------------------------------------------------
#   Health data
# ---------------------------------------------------------------------------
class BaseHealthRecord(Base, RecordMixin):
    __abstract__ = True

    id: Mapped[int] = mapped_column(primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(UtcDateTime)
    green: Mapped[int] = mapped_column()
    necrosis: Mapped[int] = mapped_column()
    health_index: Mapped[int] = mapped_column()

    @declared_attr
    def ecosystem_uid(cls) -> Mapped[str]:
        return mapped_column(
            sa.String(length=8), sa.ForeignKey("ecosystems.uid"), index=True
        )


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


# ---------------------------------------------------------------------------
#   Gaia warnings
# ---------------------------------------------------------------------------
class GaiaWarning(Base):
    __tablename__ = "warnings"
    __archive_link__ = ArchiveLink("warnings", "recent")

    id: Mapped[int] = mapped_column(primary_key=True)
    level: Mapped[gv.WarningLevel] = mapped_column(default=gv.WarningLevel.low)
    title: Mapped[str] = mapped_column(sa.String(length=256))
    description: Mapped[str] = mapped_column(sa.String(length=2048))
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
            *,
            show_solved: bool = False,
            ecosystems: str | list[str] | None = None,
            limit: int = 10,
    ) -> Sequence[Self]:
        stmt = (
            select(cls)
            .order_by(cls.created_on.desc())
            .limit(limit)
        )
        if ecosystems:
            if isinstance(ecosystems, str):
                ecosystems = ecosystems.split(",")
            stmt = stmt.where(cls.created_by.in_(ecosystems))
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


# ---------------------------------------------------------------------------
#   CRUD requests
# ---------------------------------------------------------------------------
class CrudRequest(Base, CRUDMixin):
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
