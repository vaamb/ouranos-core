from __future__ import annotations

from dataclasses import dataclass
from typing import Type

from cachetools import cached, TTLCache
import cachetools.func
from dispatcher import AsyncDispatcher
from sqlalchemy import delete, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ouranos.core import typing as ot
from ouranos.core.cache import get_cache
from ouranos.core.config.consts import (
    HARDWARE_AVAILABLE, HARDWARE_LEVELS, HARDWARE_TYPES
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
        # TODO: call GAIA
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
        stmt = (
            select(Engine)
            .where((Engine.uid == engine_id) | (Engine.sid == engine_id))
        )
        result = await session.execute(stmt)
        return result.scalars().one_or_none()

    @staticmethod
    async def get_multiple(
            session: AsyncSession,
            engines: str | list | None = None,
    ) -> list[Engine]:
        engines = engines or "all"
        if "all" in engines:
            stmt = (
                select(Engine)
                .order_by(Engine.last_seen.desc())
            )
        elif "recent" in engines:
            time_limit = time_limits()["recent"]
            stmt = (
                select(Engine)
                .where(Engine.last_seen >= time_limit)
                .order_by(Engine.last_seen.desc())
            )
        elif "connected" in engines:
            stmt = (
                select(Engine)
                .where(Engine.connected is True)
                .order_by(Engine.uid.asc())
            )
        else:
            stmt = (
                select(Engine)
                .where(
                    Engine.uid.in_(engines) |
                    Engine.sid.in_(engines)
                )
                .order_by(Engine.uid.asc())
            )
        result = await session.execute(stmt)
        return result.scalars().all()

    @staticmethod
    def get_info(session: AsyncSession, engine: Engine) -> dict:
        return engine.to_dict()


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
    ) -> list[Ecosystem]:
        ecosystems = ecosystems or "all"
        if isinstance(ecosystems, str):
            ecosystems = ecosystems.split(",")
        if "all" in ecosystems:
            stmt = (
                select(Ecosystem)
                .order_by(Ecosystem.name.asc(),
                          Ecosystem.last_seen.desc())
            )
        elif "recent" in ecosystems:
            time_limit = time_limits()["recent"]
            stmt = (
                select(Ecosystem)
                .where(Ecosystem.last_seen >= time_limit)
                .order_by(Ecosystem.status.desc(), Ecosystem.name.asc())
            )
        elif "connected" in ecosystems:
            stmt = (
                select(Ecosystem).join(Engine.ecosystems)
                .where(Engine.connected is True)
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
        return result.unique().scalars().all()

    @staticmethod
    async def get_ids(session: AsyncSession, ecosystem: str) -> ecosystemIds:
        stmt = (
            select(Ecosystem)
            .where(
                (Ecosystem.uid == ecosystem) |
                (Ecosystem.name == ecosystem)
            )
        )
        result = await session.execute(stmt)
        ecosystem_ = result.first()
        if ecosystem_:
            return ecosystemIds(ecosystem_.uid, ecosystem_.name)
        raise NoEcosystemFound

    @staticmethod
    def get_info(session: AsyncSession, ecosystem: Ecosystem) -> dict:
        return ecosystem.to_dict()

    @staticmethod
    async def get_management(
            session: AsyncSession,
            ecosystem: Ecosystem,
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
        async def cached_func(ecosystem: Ecosystem):
            management = ecosystem.management_dict()
            return {
                "uid": ecosystem.uid,
                "name": ecosystem.name,
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
                "environment_data": await sensor_data(ecosystem.uid, "environment"),
                "plants_data": await sensor_data(ecosystem.uid, "plants"),
            }
        return await cached_func(ecosystem)

    @staticmethod
    def get_light_info(ecosystem: Ecosystem) -> dict:
        if ecosystem.light:
            return ecosystem.light.to_dict()
        return {}

    @staticmethod
    async def get_sensors_data_skeleton(
            session: AsyncSession,
            ecosystem: Ecosystem,
            time_window: timeWindow,
            level: ot.HARDWARE_LEVELS | list[ot.HARDWARE_LEVELS] | None = None,
    ) -> dict:
        level = level or "all"

        @cached(cache_sensors_data_skeleton)
        async def inner_func(
                ecosystem_id: str,
                time_window: timeWindow,
                level: list[ot.HARDWARE_LEVELS],
        ) -> list:
            stmt = (
                select(Hardware).join(SensorHistory.sensor)
                .filter(Hardware.level.in_(level))
                .filter(Hardware.ecosystem_uid == ecosystem_id)
                .filter((SensorHistory.timestamp > time_window.start) &
                        (SensorHistory.timestamp <= time_window.end))
            )
            result = await session.execute(stmt)
            sensors = result.unique().scalars().all()
            temp = {}
            for sensor_ in sensors:
                for measure_ in sensor_.measure:
                    try:
                        temp[measure_.name][sensor_.uid] = sensor_.name
                    except KeyError:
                        temp[measure_.name] = {sensor_.uid: sensor_.name}
            order = [
                "temperature", "humidity", "lux", "dew_point", "absolute_moisture",
                "moisture"
            ]
            return [{
                "measure": measure_,
                "sensors": [{
                    "uid": sensor_,
                    "name": temp[measure_][sensor_]
                } for sensor_ in temp[measure_]]
            } for measure_ in {
                key: temp[key] for key in order if temp.get(key)
            }]

        if "all" in level:
            level = HARDWARE_LEVELS
        elif isinstance(level, str):
            level = level.split(",")
        return {
            "uid": ecosystem.uid,
            "name": ecosystem.name,
            "level": level,
            "sensors_skeleton": await inner_func(
                ecosystem_id=ecosystem.uid, time_window=time_window,
                level=level
            )
        }

    @staticmethod
    def get_environment_parameters_info(
            session: AsyncSession,
            ecosystem: Ecosystem,
    ) -> dict:
        #parameters = await environmental_parameter.get_multiple(session, e.uid)
        return {
            "uid": ecosystem.uid,
            "name": ecosystem.name,
            "day": ecosystem.day_start,
            "night": ecosystem.night_start,
            "parameters": [
                parameter.to_dict()
                for parameter in ecosystem.environment_parameters
            ]
        }

    @staticmethod
    def get_plants_info(
            session: AsyncSession,
            ecosystem: Ecosystem,
    ) -> dict:
        return {
            "ecosystem_uid": ecosystem.uid,
            "ecosystem_name": ecosystem.name,
            "plants": [
                plant.to_dict()
                for plant in ecosystem.plants
            ]
        }

    @staticmethod
    async def get_hardware_info(
            session: AsyncSession,
            ecosystem: Ecosystem,
            level: ot.HARDWARE_LEVELS | list[ot.HARDWARE_LEVELS] | None = None,
            hardware_type: ot.HARDWARE_TYPES | list[ot.HARDWARE_TYPES] | None = None
    ) -> dict:
        if level is None or "all" in level:
            level = HARDWARE_LEVELS
        if hardware_type is None or "all" in hardware_type:
            hardware_type = HARDWARE_TYPES
        elif "actuators" in hardware_type:
            types = list(HARDWARE_TYPES)
            hardware_type = types.remove("sensor")

        stmt = (
            select(Hardware).join(Ecosystem)
            .filter(Ecosystem.uid == ecosystem.uid)
            .filter(Hardware.type.in_(hardware_type))
            .filter(Hardware.level.in_(level))
            .order_by(Hardware.type)
            .order_by(Hardware.level)
        )
        result = await session.execute(stmt)
        return {
                "ecosystem_uid": ecosystem.uid,
                "ecosystem_name": ecosystem.name,
                "hardware": [h.to_dict() for h in result.scalars().all()]
            }

    @staticmethod
    async def turn_actuator(
            dispatcher: AsyncDispatcher,
            ecosystem_uid: str,
            actuator: ot.ACTUATOR_TYPES,
            mode: ot.ACTUATOR_MODE = "automatic",
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
            mode: ot.ACTUATOR_MODE = "automatic",
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

    # TODO: call GAIA
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
            parameter: str,
    ) -> EnvironmentParameter | None:
        stmt = (
            select(EnvironmentParameter)
            .where(
                EnvironmentParameter.ecosystem_uid == uid,
                EnvironmentParameter.parameter == parameter
            )
        )
        result = await session.execute(stmt)
        return result.scalars().one_or_none()

    @staticmethod
    async def get_multiple(
             session: AsyncSession,
             uids: list | None = None,
             parameters: list | None = None,
    ) -> list[EnvironmentParameter]:
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
        if not (uid or parameter):
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
    def _get_query(
            hardware_uid: str | list | None = None,
            ecosystem_uid: str | list | None = None,
            levels: ot.HARDWARE_LEVELS | list[ot.HARDWARE_LEVELS] | None = None,
            types: ot.HARDWARE_TYPES | list[ot.HARDWARE_TYPES] | None = None,
            models: str | list | None = None,
    ):
        query = select(Hardware)
        l = locals()
        args = "hardware_uid", "ecosystem_uid", "levels", "types", "models"
        for arg in args:
            value = l.get(arg)
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
            levels: ot.HARDWARE_LEVELS | list[ot.HARDWARE_LEVELS] | None = None,
            types: ot.HARDWARE_TYPES | list[ot.HARDWARE_TYPES] | None = None,
            models: str | list | None = None,
    ) -> list[Hardware]:
        stmt = hardware._get_query(
            hardware_uids, ecosystem_uids, levels, types, models
        )
        result = await session.execute(stmt)
        return result.unique().scalars().all()

    @staticmethod
    def get_info(
            session: AsyncSession,
            hardware_obj: Hardware
    ) -> dict:
        return hardware_obj.to_dict()

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
        stmt = hardware._get_query(hardware_uid=uid)
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
            levels: ot.HARDWARE_LEVELS | list[ot.HARDWARE_LEVELS] | None = None,
            models: str | list | None = None,
            time_window: timeWindow = None,
    ) -> list[Hardware]:
        stmt = hardware._get_query(
            hardware_uids, ecosystem_uids, levels, "sensor", models
        )
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
        return result.unique().scalars().all()

    @staticmethod
    async def _get_data_record(
            session: AsyncSession,
            sensor_obj: Hardware,
            measure: str,
            time_window: timeWindow
    ) -> list:
        @cached(cache_sensors_data_raw)
        async def cached_func(
                sensor_obj: Hardware,
                measure: str,
                time_window: timeWindow
        ) -> list:
            stmt = (
                select(SensorHistory.timestamp, SensorHistory.value)
                .filter(SensorHistory.measure == measure)
                .filter(SensorHistory.sensor_uid == sensor_obj.uid)
                .filter((SensorHistory.timestamp > time_window[0]) &
                        (SensorHistory.timestamp <= time_window[1]))
            )
            result = await session.execute(stmt)
            return result.all()
        return await cached_func(sensor_obj, measure, time_window)

    @staticmethod
    async def _get_historic_data(
            session: AsyncSession,
            sensor_obj: Hardware,
            time_window: timeWindow,
            measures: str | list | None = None,
    ) -> list:
        if measures is None or "all" in measures:
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
            if measures is None or "all" in measures:
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
    async def get_measure(
            session: AsyncSession,
            measure_name: str
    ) -> Measure | None:
        stmt = select(Measure).where(Measure.name == measure_name)
        result = await session.execute(stmt)
        return result.scalars().one_or_none()

    @staticmethod
    async def get_unit(session: AsyncSession, measure_name: str) -> str:
        stmt = (
            select(Measure)
            .filter(Measure.name == measure_name)
        )
        result = await session.execute(stmt)
        measure_ = result.scalars().one_or_none()
        if measure_:
            return measure_.unit
        return ""

    @staticmethod
    async def get_multiple(
            session: AsyncSession,
            measures_name: list[str] | None = None
    ) -> list[Measure]:
        stmt = select(Measure)
        if measures_name:
            stmt = stmt.where(Measure.name.in_(measures_name))
        result = await session.execute(stmt)
        return result.scalars().all()

    @staticmethod
    def get_info(session: AsyncSession, measure_obj: Measure) -> list[dict]:
        return measure_obj.to_dict()


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
        # TODO: call GAIA
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


class plant:
    @staticmethod
    async def get_multiple(
            session: AsyncSession,
            plants_name: list[str] | None = None
    ) -> list[Plant]:
        stmt = select(Plant)
        if plants_name:
            stmt = stmt.where(Plant.name.in_(plants_name))
        result = await session.execute(stmt)
        return result.scalars().all()


@cachetools.func.ttl_cache(ttl=60)
async def get_recent_warnings(
        session: AsyncSession,
        limit: int = 10
) -> list[GaiaWarning]:
    time_limit = time_limits()["warnings"]
    stmt = (
        select(GaiaWarning)
        .where(GaiaWarning.created >= time_limit)
        .where(GaiaWarning.is_solved is False)
        .order_by(GaiaWarning.emergency.desc())
        .order_by(GaiaWarning.id)
        .with_entities(
            GaiaWarning.created, GaiaWarning.emergency, GaiaWarning.title
        )
        .limit(limit)
    )
    result = await session.execute(stmt)
    return result.scalars().all()
