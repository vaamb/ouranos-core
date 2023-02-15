from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Sequence, Type

from cachetools import cached, TTLCache
import cachetools.func
from dispatcher import AsyncDispatcher
from sqlalchemy import delete, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ouranos.core.cache import get_cache
from ouranos.core.config.consts import (
    HARDWARE_AVAILABLE, HARDWARE_LEVELS
)
from ouranos.core.database.models.gaia import (
    Ecosystem, Engine, EnvironmentParameter, GaiaWarning, Hardware, Health,
    Light, Measure, Plant, SensorHistory
)
from ouranos.sdk.api.exceptions import NoEcosystemFound
from ouranos.sdk.api.utils import time_limits, timeWindow, create_time_window


max_ecosystems = 32

cache_ecosystem_info = TTLCache(maxsize=max_ecosystems, ttl=60)
cache_sensors_data_skeleton = TTLCache(maxsize=max_ecosystems, ttl=900)
cache_sensors_data_raw = TTLCache(maxsize=max_ecosystems * 32, ttl=900)
cache_sensors_data_average = TTLCache(maxsize=max_ecosystems, ttl=300)
cache_sensors_data_summary = TTLCache(maxsize=max_ecosystems * 2, ttl=300)


ACTUATOR_MODE_CHOICES = Literal["on", "off", "automatic"]
ACTUATOR_TYPES_CHOICES = Literal[
    "light", "heater", "cooler", "humidifier", "dehumidifier"
]
HARDWARE_LEVELS_CHOICES = Literal["plants", "environment"]
HARDWARE_TYPES_CHOICES = Literal[
    "sensor", "light", "heater", "cooler", "humidifier", "dehumidifier"
]


@dataclass(frozen=True)
class ecosystemIds:
    uid: str
    name: str

    def __iter__(self):
        return iter((self.uid, self.name))


class _gaia_abc:
    _model_cls: Type[Ecosystem | Engine | EnvironmentParameter | Hardware | Light]

    @classmethod
    async def create(
            cls,
            session: AsyncSession,
            values: dict,
    ) -> _model_cls:
        model = cls._model_cls(**values)
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
            update(cls._model_cls)
            .where(cls._model_cls.uid == uid)
            .values(**values)
        )
        await session.execute(stmt)

    @classmethod
    async def delete(
            cls,
            session: AsyncSession,
            uid: str,
    ) -> None:
        stmt = delete(cls._model_cls).where(cls._model_cls.uid == uid)
        await session.execute(stmt)

    @classmethod
    async def update_or_create(
            cls,
            session: AsyncSession,
            values: dict | None = None,
            uid: str | None = None,
    ) -> _model_cls:
        values = values or {}
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

    @staticmethod
    async def get(
            session: AsyncSession,
            uid: str,
    ) -> _model_cls | None:
        raise NotImplementedError

    @staticmethod
    async def get_multiple(
            session: AsyncSession,
            uid: str | list | None = None,
    ) -> Sequence[_model_cls]:
        raise NotImplementedError


# ---------------------------------------------------------------------------
#   Engine-related APIs
# ---------------------------------------------------------------------------
class engine(_gaia_abc):
    _model_cls = Engine

    @staticmethod
    async def get(
            session: AsyncSession,
            engine_id: str,
    ) -> Engine | None:
        stmt = select(Engine).where(
            (Engine.uid == engine_id)
            | (Engine.sid == engine_id)
        )
        result = await session.execute(stmt)
        return result.scalars().one_or_none()

    @staticmethod
    async def get_multiple(
            session: AsyncSession,
            engines: str | list | None = None,
    ) -> Sequence[Engine]:
        if engines is None:
            stmt = (
                select(Engine)
                .order_by(Engine.last_seen.desc())
            )
            result = await session.execute(stmt)
            return result.scalars().all()
        if isinstance(engines, str):
            engines = engines.split(",")
        if "recent" in engines:
            time_limit = time_limits()["recent"]
            stmt = (
                select(Engine)
                .where(Engine.last_seen >= time_limit)
                .order_by(Engine.last_seen.desc())
            )
        elif "connected" in engines:
            stmt = (
                select(Engine)
                .where(Engine.connected == True)  # noqa
                .order_by(Engine.uid.asc())
            )
        else:
            stmt = (
                select(Engine)
                .where(
                    (Engine.uid.in_(engines))
                    | (Engine.sid.in_(engines))
                )
                .order_by(Engine.uid.asc())
            )
        result = await session.execute(stmt)
        return result.scalars().all()


# ---------------------------------------------------------------------------
#   Ecosystem-related APIs
# ---------------------------------------------------------------------------
class ecosystem(_gaia_abc):
    _model_cls = Ecosystem

    @staticmethod
    async def get(
            session: AsyncSession,
            ecosystem_id: str,
    ) -> Ecosystem | None:
        stmt = (
            select(Ecosystem)
            .where((Ecosystem.uid == ecosystem_id) | (Ecosystem.name == ecosystem_id))
        )
        result = await session.execute(stmt)
        return result.unique().scalars().one_or_none()

    @staticmethod
    async def get_multiple(
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
            time_limit = time_limits()["recent"]
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
                select(Ecosystem).join(Engine.ecosystems)
                .where(Ecosystem.uid.in_(ecosystems) |
                       Ecosystem.name.in_(ecosystems))
                .order_by(Ecosystem.last_seen.desc(), Ecosystem.name.asc())
            )
        result = await session.execute(stmt)
        return result.scalars().all()

    @staticmethod
    async def get_ids(session: AsyncSession, ecosystem_id: str) -> ecosystemIds:
        stmt = (
            select(Ecosystem)
            .where(
                (Ecosystem.uid == ecosystem_id) |
                (Ecosystem.name == ecosystem_id)
            )
        )
        result = await session.execute(stmt)
        ecosystem_ = result.first()
        if ecosystem_:
            return ecosystemIds(ecosystem_.uid, ecosystem_.name)
        raise NoEcosystemFound

    @staticmethod
    async def get_management(
            session: AsyncSession,
            ecosystem_obj: Ecosystem,
    ) -> dict:
        limits = time_limits()

        async def sensor_data(ecosystem_uid: str, level) -> bool:
            stmt = (
                select(Hardware)
                .where(Hardware.ecosystem_uid == ecosystem_uid)
                .where(
                    Hardware.type == "sensor",
                    Hardware.level == level
                )
                .filter(Hardware.last_log >= limits["sensors"])
            )
            result = await session.execute(stmt)
            return bool(result.first())

        @cached(cache_ecosystem_info)
        async def inner_func(_ecosystem_obj: Ecosystem):
            management = ecosystem_obj.management_dict()
            return {
                "uid": ecosystem_obj.uid,
                "name": ecosystem_obj.name,
                "sensors": management.get("sensors", False),
                "light": management.get("light", False),
                "climate": management.get("climate", False),
                "watering": management.get("watering", False),
                "health": management.get("health", False),
                "alarms": management.get("alarms", False),
                "webcam": management.get("webcam", False),
                "switches": any((
                    management.get("climate"), management.get("light")
                )),
                "environment_data": await sensor_data(ecosystem_obj.uid, "environment"),
                "plants_data": await sensor_data(ecosystem_obj.uid, "plants"),
            }
        return await inner_func(ecosystem_obj)

    @staticmethod
    async def get_sensors_data_skeleton(
            session: AsyncSession,
            ecosystem_obj: Ecosystem,
            time_window: timeWindow,
            level: HARDWARE_LEVELS_CHOICES | list[HARDWARE_LEVELS_CHOICES] | None = None,
    ) -> dict:
        @cached(cache_sensors_data_skeleton)
        async def inner_func(
                ecosystem_uid: str,
                _time_window: timeWindow,
                _level: list[HARDWARE_LEVELS_CHOICES] | None = None,
        ) -> list:
            stmt = (
                select(Hardware).join(SensorHistory.sensor)
                .where(Hardware.ecosystem_uid == ecosystem_uid)
                .where(
                    (SensorHistory.timestamp > time_window.start)
                    & (SensorHistory.timestamp <= time_window.end)
                )
            )
            if level:
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
            order = (
                "temperature", "humidity", "lux", "dew_point", "absolute_moisture",
                "moisture"
            )
            return [{
                "measure": measure_name,
                "sensors": [{
                    "uid": sensor_uid,
                    "name": temp[measure_name][sensor_uid]
                } for sensor_uid in temp[measure_name]]
            } for measure_name in {
                key: temp[key] for key in order if temp.get(key)
            }]

        if isinstance(level, str):
            level = level.split(",")
        return {
            "uid": ecosystem_obj.uid,
            "name": ecosystem_obj.name,
            "level": HARDWARE_LEVELS if level is None else level,
            "sensors_skeleton": await inner_func(
                ecosystem_uid=ecosystem_obj.uid, time_window=time_window,
                level=level
            )
        }

    @staticmethod
    async def turn_actuator(
            dispatcher: AsyncDispatcher,
            ecosystem_uid: str,
            actuator: ACTUATOR_TYPES_CHOICES,
            mode: ACTUATOR_MODE_CHOICES = "automatic",
            countdown: float = 0.0,
    ) -> None:
        # TODO: select room using db
        await dispatcher.emit(
            "gaia", "turn_actuator", ecosystem_uid=ecosystem_uid,
            actuator=actuator, mode=mode, countdown=countdown
        )

    @staticmethod
    async def turn_light(
            dispatcher: AsyncDispatcher,
            ecosystem_uid: str,
            mode: ACTUATOR_MODE_CHOICES = "automatic",
            countdown: float = 0.0,
    ) -> None:
        await ecosystem.turn_actuator(
            dispatcher, ecosystem_uid, "light", mode, countdown
        )


# ---------------------------------------------------------------------------
#   Environmental parameters-related APIs
# ---------------------------------------------------------------------------
class environmental_parameter(_gaia_abc):
    _model_cls = EnvironmentParameter

    @classmethod
    async def create(
            cls,
            session: AsyncSession,
            parameters_info: dict,
    ) -> EnvironmentParameter:
        return await super().create(session, parameters_info)

    @classmethod
    async def update(
            cls,
            session: AsyncSession,
            parameter_info: dict,
            uid: str | None = None,
            parameter: str | None = None,
    ) -> None:
        parameter_info = parameter_info or {}
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

    @staticmethod
    async def get(
            session: AsyncSession,
            uid: str,
            parameter: str | None = None,
    ) -> Sequence[EnvironmentParameter]:
        stmt = (
            select(EnvironmentParameter)
            .where(EnvironmentParameter.ecosystem_uid == uid)
        )
        if parameter:
            stmt = stmt.where(EnvironmentParameter.parameter == parameter)
        result = await session.execute(stmt)
        return result.scalars().all()

    @staticmethod
    async def get_multiple(
             session: AsyncSession,
             uids: list | None = None,
             parameters: list | None = None,
    ) -> Sequence[EnvironmentParameter]:
        stmt = select(EnvironmentParameter)
        if uids:
            stmt = stmt.where(EnvironmentParameter.ecosystem_uid.in_(uids))
        if parameters:
            stmt = stmt.where(EnvironmentParameter.parameter.in_(parameters))
        result = await session.execute(stmt)
        return result.scalars().all()

    @staticmethod
    async def update_or_create(
            session: AsyncSession,
            parameter_info: dict | None = None,
            uid: str | None = None,
    ) -> EnvironmentParameter:
        parameter_info = parameter_info or {}
        uid = uid or parameter_info.pop("uid", None)
        parameter = parameter_info.get("parameter")
        if not (uid and parameter):
            raise ValueError(
                "Provide uid and parameter either as a argument or as a key in the "
                "updated info"
            )
        environment_parameter = await environmental_parameter.get(
            session, uid=uid, parameter=parameter
        )
        if not environment_parameter:
            parameter_info["ecosystem_uid"] = uid
            parameter_info["parameter"] = parameter
            environment_parameter = await environmental_parameter.create(
                session, parameter_info
            )
        elif parameter_info:
            environment_parameter = await environmental_parameter.update(
                session, parameter_info, uid
            )
        return environment_parameter


# ---------------------------------------------------------------------------
#   Hardware-related APIs
# ---------------------------------------------------------------------------
class hardware(_gaia_abc):
    _model_cls = Hardware

    @staticmethod
    async def _attach_relationships(
            session: AsyncSession,
            hardware_uid: str,
            relative_list: list,
            relationship_api_cls,
            relative_attr: str,
    ) -> None:
        objs = await relationship_api_cls.get_multiple(session, relative_list)
        hardware_obj = await hardware.get(session, hardware_uid=hardware_uid)
        relatives = getattr(hardware_obj, relative_attr)
        for obj in objs:
            if obj not in relatives:
                relatives.append(obj)
        session.add(hardware_obj)
        await session.commit()

    @staticmethod
    async def attach_relationships(
            session: AsyncSession,
            hardware_uid: str,
            measures: list | str,
            plants: list | str,
    ) -> None:
        if measures:
            if isinstance(measures, str):
                measures = [measures]
            measures = [m.replace("_", " ") for m in measures]
            await hardware._attach_relationships(
                session, hardware_uid, measures, measure, "measures"
            )
        if plants:
            if isinstance(plants, str):
                plants = [plants]
            await hardware._attach_relationships(
                session, hardware_uid, plants, plant, "plants"
            )

    @classmethod
    async def create(
            cls,
            session: AsyncSession,
            values: dict,
    ) -> Hardware:
        measures = values.pop("measures", [])
        plants = values.pop("plants", [])
        hardware_obj = await super().create(session, values)
        if any((measures, plants)):
            uid = values["uid"]
            await hardware.attach_relationships(session, uid, measures, plants)
            hardware_obj = await hardware.get(session, uid)
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
            await hardware.attach_relationships(session, uid, measures, plants)

    @staticmethod
    async def get(
            session: AsyncSession,
            hardware_uid: str,
    ) -> Hardware | None:
        stmt = select(Hardware).where(Hardware.uid == hardware_uid)
        result = await session.execute(stmt)
        return result.unique().scalars().one_or_none()

    @staticmethod
    def generate_query(
            hardware_uid: str | list | None = None,
            ecosystem_uid: str | list | None = None,
            level: HARDWARE_LEVELS_CHOICES | list[HARDWARE_LEVELS_CHOICES] | None = None,
            type: HARDWARE_TYPES_CHOICES | list[HARDWARE_TYPES_CHOICES] | None = None,
            model: str | list | None = None,
    ):
        uid = hardware_uid
        query = select(Hardware)
        local_vars = locals()
        args = "uid", "ecosystem_uid", "level", "type", "model"
        for arg in args:
            value = local_vars.get(arg)
            if value:
                if isinstance(value, str):
                    value = value.split(",")
                hardware_attr = getattr(Hardware, arg)
                query = query.where(hardware_attr.in_(value))
        return query

    @staticmethod
    async def get_multiple(
            session: AsyncSession,
            hardware_uids: str | list | None = None,
            ecosystem_uids: str | list | None = None,
            levels: HARDWARE_LEVELS_CHOICES | list[HARDWARE_LEVELS_CHOICES] | None = None,
            types: HARDWARE_TYPES_CHOICES | list[HARDWARE_TYPES_CHOICES] | None = None,
            models: str | list | None = None,
    ) -> Sequence[Hardware]:
        stmt = hardware.generate_query(
            hardware_uids, ecosystem_uids, levels, types, models
        )
        result = await session.execute(stmt)
        return result.unique().scalars().all()

    @staticmethod
    def get_models_available() -> list:
        return HARDWARE_AVAILABLE


# ---------------------------------------------------------------------------
#   Sensor-related APIs
# ---------------------------------------------------------------------------
class sensor:
    """Sensors are a specific type of hardware so their creation, update and
    deletion are handled by the class `hardware`"""
    @staticmethod
    async def get(
            session: AsyncSession,
            uid: str,
            time_window: timeWindow | None = None,
    ) -> Hardware | None:
        stmt = hardware.generate_query(hardware_uid=uid)
        if time_window:
            stmt = (
                stmt.join(SensorHistory.sensor)
                .where(
                    (SensorHistory.timestamp > time_window.start) &
                    (SensorHistory.timestamp <= time_window.end)
                )
                .distinct()
            )
        result = await session.execute(stmt)
        return result.unique().scalars().one_or_none()

    @staticmethod
    async def get_multiple(
            session: AsyncSession,
            hardware_uids: str | list | None = None,
            ecosystem_uids: str | list | None = None,
            levels: HARDWARE_LEVELS_CHOICES | list[HARDWARE_LEVELS_CHOICES] | None = None,
            models: str | list | None = None,
            time_window: timeWindow = None,
    ) -> Sequence[Hardware]:
        stmt = hardware.generate_query(
            hardware_uids, ecosystem_uids, levels, "sensor", models
        )
        if time_window:
            stmt = (
                stmt.join(SensorHistory.sensor)
                .where(
                    (SensorHistory.timestamp > time_window.start)
                    & (SensorHistory.timestamp <= time_window.end)
                )
                .distinct()
            )
        result = await session.execute(stmt)
        return result.unique().scalars().all()

    @staticmethod
    async def _get_data_record(
            session: AsyncSession,
            sensor_obj: Hardware,
            measure_name: str,
            time_window: timeWindow
    ) -> list:
        @cached(cache_sensors_data_raw)
        async def inner_func(
                _sensor_obj: Hardware,
                _measure_name: str,
                _time_window: timeWindow
        ) -> list:
            stmt = (
                select(SensorHistory)
                .where(SensorHistory.measure == measure_name)
                .where(SensorHistory.sensor_uid == sensor_obj.uid)
                .where(
                    (SensorHistory.timestamp > time_window.start)
                    & (SensorHistory.timestamp <= time_window.end)
                )
            )
            result = await session.execute(stmt)
            records: Sequence[SensorHistory] = result.scalars().all()
            return [(record.timestamp, record.value) for record in records]
        return await inner_func(sensor_obj, measure_name, time_window)

    @staticmethod
    async def _get_historic_data(
            session: AsyncSession,
            sensor_obj: Hardware,
            time_window: timeWindow,
            measures: str | list | None = None,
    ) -> list:
        if measures is None:
            measures = [measure_.name for measure_ in sensor_obj.measures]
        elif isinstance(measures, str):
            measures = measures.split(",")
        rv = []
        for measure_ in measures:
            records = await sensor._get_data_record(
                session, sensor_obj, measure_, time_window
            )
            if records:
                rv.append({
                    "measure": measure_,
                    "unit": await measure.get_unit(session, measure_),
                    "records": records,
                })
        return rv

    @staticmethod
    async def _get_current_data(
            session: AsyncSession,
            sensor_obj: Hardware,
            measures: str | list | None = None,
    ) -> list:
        try:
            ecosystem_uid = sensor_obj.ecosystem_uid
            cache = get_cache("sensors_data")
            ecosystem_ = cache[ecosystem_uid]
        except KeyError:
            return []
        else:
            if measures is None:
                measures = [measure_.name for measure_ in sensor_obj.measures]
            elif isinstance(measures, str):
                measures = measures.split(",")
            rv = []
            for measure_ in measures:
                value = ecosystem_["data"].get(sensor_obj.uid, {}).get(measure_, None)
                if value:
                    rv.append({
                        "measure": measure_,
                        "unit": await measure.get_unit(session, measure_),
                        "value": value,
                    })
            return rv

    @staticmethod
    async def get_overview(
            session: AsyncSession,
            sensor_obj: Hardware,
            measures: str | list | None = None,
            current_data: bool = True,
            historic_data: bool = True,
            time_window: timeWindow = None,
    ) -> dict:
        assert sensor_obj.type == "sensor"
        rv = sensor_obj.to_dict()
        if current_data or historic_data:
            rv.update({"data": {}})
            if current_data:
                data = await sensor._get_current_data(session, sensor_obj, measures)
                if data:
                    cache = get_cache("sensors_data")
                    rv["data"].update({
                        "current": {
                            "timestamp": cache[sensor_obj.ecosystem_uid]["datetime"],
                            "data": data,
                        }
                    })
                else:
                    rv["data"].update({"current": None})
            if historic_data:
                if not time_window:
                    time_window = create_time_window()
                data = await sensor._get_historic_data(
                    session, sensor_obj, time_window, measures
                )
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
    def get_current_data(ecosystem_uid: str | None = None) -> dict:
        cache = get_cache("sensors_data")
        if ecosystem_uid:
            return cache.get(ecosystem_uid, {})
        return {**cache}

    @staticmethod
    def clear_current_data(key: str | None = None) -> None:
        cache = get_cache("sensors_data")
        if key:
            del cache[key]
        else:
            cache.clear()

    @staticmethod
    def update_current_data(data: dict) -> None:
        cache = get_cache("sensors_data")
        cache.update(data)

    @staticmethod
    async def create_records(
            session: AsyncSession,
            values: list[dict],
    ) -> None:
        stmt = insert(SensorHistory).values(values)
        await session.execute(stmt)


class measure:
    @staticmethod
    async def get_unit(session: AsyncSession, measure_name: str) -> str | None:
        stmt = (
            select(Measure)
            .filter(Measure.name == measure_name)
        )
        result = await session.execute(stmt)
        measure_obj = result.scalars().one_or_none()
        if measure_obj is not None:
            return measure_obj.unit
        return None

    @staticmethod
    async def get(
            session: AsyncSession,
            name: str
    ) -> Measure | None:
        stmt = select(Measure).where(Measure.name == name)
        result = await session.execute(stmt)
        return result.scalars().one_or_none()

    @staticmethod
    async def get_multiple(
            session: AsyncSession,
            names: list[str] | None = None
    ) -> Sequence[Measure]:
        stmt = select(Measure)
        if names:
            stmt = stmt.where(Measure.name.in_(names))
        result = await session.execute(stmt)
        return result.scalars().all()


# ---------------------------------------------------------------------------
#   Light-related APIs
# ---------------------------------------------------------------------------
class light(_gaia_abc):
    _model_cls = Light

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
            update(Light)
            .where(Light.ecosystem_uid == ecosystem_uid)
            .values(**values)
        )
        await session.execute(stmt)

    @staticmethod
    async def get(
            session: AsyncSession,
            ecosystem_uid: str,
    ) -> Light | None:
        stmt = select(Light).where(Light.ecosystem_uid == ecosystem_uid)
        result = await session.execute(stmt)
        return result.one_or_none()

    @staticmethod
    async def get_multiple(
            session: AsyncSession,
            ecosystem_uids: list[str] | None = None,
    ) -> Sequence[Light]:
        stmt = select(Light)
        if ecosystem_uids:
            stmt = stmt.where(Light.ecosystem_uid.in_(ecosystem_uids))
        result = await session.execute(stmt)
        return result.scalars().all()

    @classmethod
    async def update_or_create(
            cls,
            session: AsyncSession,
            values: dict | None = None,
            ecosystem_uid: str | None = None,
    ) -> Light:
        values = values or {}
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


# ---------------------------------------------------------------------------
#   Health-related APIs
# ---------------------------------------------------------------------------
class health:
    @staticmethod
    async def create_records(
            session: AsyncSession,
            values: list[dict],
    ) -> None:
        stmt = insert(Health).values(values)
        await session.execute(stmt)


class plant(_gaia_abc):
    _model_cls = Plant

    @staticmethod
    async def get(
            session: AsyncSession,
            plant_id: str
    ) -> Plant | None:
        stmt = select(Plant).where(
            (Plant.name.in_(plant_id))
            | (Plant.uid.in_(plant_id))
        )
        result = await session.execute(stmt)
        return result.scalars().one_or_none()

    @staticmethod
    async def get_multiple(
            session: AsyncSession,
            plants_id: list[str] | None = None
    ) -> Sequence[Plant]:
        stmt = select(Plant)
        if plants_id:
            stmt = stmt.where(
                (Plant.name.in_(plants_id))
                | (Plant.uid.in_(plants_id))
            )
        result = await session.execute(stmt)
        return result.scalars().all()


@cachetools.func.ttl_cache(ttl=60)
async def get_recent_warnings(
        session: AsyncSession,
        limit: int = 10
) -> Sequence[GaiaWarning]:
    time_limit = time_limits()["warnings"]
    stmt = (
        select(GaiaWarning)
        .where(GaiaWarning.created_on >= time_limit)
        .where(GaiaWarning.solved == False)  # noqa
        .order_by(GaiaWarning.level.desc())
        .order_by(GaiaWarning.id)
        .limit(limit)
    )
    result = await session.execute(stmt)
    return result.scalars().all()
