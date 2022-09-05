from __future__ import annotations

from collections import namedtuple

from cachetools import cached, TTLCache
import cachetools.func
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api.exceptions import NoEcosystemFound
from src.core.api.utils import time_limits, timeWindow, create_time_window
from src.core.cache import get_cache
from src.core.consts import (
    HARDWARE_AVAILABLE, HARDWARE_LEVELS, HARDWARE_TYPES
)
from src.core import typing as ot
from src.core.database.models.gaia import (
    Ecosystem, Engine, EnvironmentParameter, GaiaWarning, Hardware, Health,
    Light, Measure, Plant, SensorHistory
)


# TODO: move this into config
max_ecosystems = 32

cache_ecosystem_info = TTLCache(maxsize=max_ecosystems, ttl=60)
cache_sensors_data_skeleton = TTLCache(maxsize=max_ecosystems, ttl=900)
cache_sensors_data_raw = TTLCache(maxsize=max_ecosystems * 32, ttl=900)
cache_sensors_data_average = TTLCache(maxsize=max_ecosystems, ttl=300)
cache_sensors_data_summary = TTLCache(maxsize=max_ecosystems * 2, ttl=300)


class ecosystemIds(namedtuple("ecosystemIds", ("uid", "name"))):
    __slots__ = ()


async def _create_entry(
        session: AsyncSession,
        model_class,
        model_info: dict,
):
    # TODO: call GAIA
    model = model_class(**model_info)
    session.add(model)
    return model


async def _update_entry(
        session: AsyncSession,
        model_class,
        model_info: dict,
        uid: str | None = None,
) -> None:
    # TODO: call GAIA
    uid = uid or model_info.pop("uid", None)
    if not uid:
        raise ValueError(
            "Provide uid either as a parameter or as a key in the updated info"
        )
    stmt = (
        update(model_class)
        .where(model_class.uid == uid)
        .values(**model_info)
    )
    await session.execute(stmt)


async def _delete_entry(
        session: AsyncSession,
        model_class,
        uid: str | None = None,
) -> None:
    # TODO: call GAIA
    stmt = delete(model_class).where(model_class.uid == uid)
    await session.execute(stmt)


async def _update_or_create(
        session: AsyncSession,
        api_class,
        info: dict | None = None,
        uid: str | None = None,
):
    info = info or {}
    uid = uid or info.pop("uid", None)
    if not uid:
        raise ValueError(
            "Provide uid either as an argument or as a key in the updated info"
        )
    obj = await api_class.get(session, uid)
    if not obj:
        info["uid"] = uid
        obj = await api_class.create(session, info)
    elif info:
        await api_class.update(session, info, uid)
    return obj


# ---------------------------------------------------------------------------
#   Engine-related APIs
# ---------------------------------------------------------------------------
class engine:
    @staticmethod
    async def create(
            session: AsyncSession,
            engine_info: dict,
    ) -> Engine:
        return await _create_entry(session, Engine, engine_info)

    @staticmethod
    async def update(
            session: AsyncSession,
            engine_info: dict,
            uid: str | None = None,
    ) -> None:
        await _update_entry(session, Engine, engine_info, uid)

    @staticmethod
    async def delete(
            session: AsyncSession,
            uid: str,
    ) -> None:
        await _delete_entry(session, Engine, uid)

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
                .where(Engine.connected)
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
    async def update_or_create(
            session: AsyncSession,
            engine_info: dict | None = None,
            uid: str | None = None,
    ) -> Engine:
        return await _update_or_create(
            session, api_class=engine, info=engine_info, uid=uid
        )

    @staticmethod
    def get_info(session: AsyncSession, engine: Engine) -> dict:
        return engine.to_dict()


# ---------------------------------------------------------------------------
#   Ecosystem-related APIs
# ---------------------------------------------------------------------------
class ecosystem:
    @staticmethod
    async def create(
            session: AsyncSession,
            ecosystem_info: dict,
    ) -> Ecosystem:
        return await _create_entry(session, Ecosystem, ecosystem_info)

    @staticmethod
    async def update(
            session: AsyncSession,
            ecosystem_info: dict,
            uid: str | None = None,
    ) -> None:
        await _update_entry(session, Ecosystem, ecosystem_info, uid)

    @staticmethod
    async def delete(
            session: AsyncSession,
            uid: str
    ) -> None:
        await _delete_entry(session, Ecosystem, uid)

    @staticmethod
    async def get(
            session: AsyncSession,
            ecosystem_id: str,
    ) -> Ecosystem | None:
        ecosystem_id = (ecosystem_id, )
        stmt = (
            select(Ecosystem)
            .where(Ecosystem.uid.in_(ecosystem_id) | Ecosystem.name.in_(ecosystem_id))
        )
        result = await session.execute(stmt)
        return result.unique().scalars().one_or_none()

    @staticmethod
    async def get_multiple(
            session: AsyncSession,
            ecosystems: str | list | None = None,
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
                .where(Engine.connected)
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
    async def update_or_create(
            session: AsyncSession,
            ecosystem_info: dict | None = None,
            uid: str | None = None,
    ) -> Ecosystem:
        return await _update_or_create(
            session, api_class=ecosystem, info=ecosystem_info, uid=uid
        )

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
    def get_light_info(session: AsyncSession, ecosystem: Ecosystem) -> dict:
        return ecosystem.light.first().to_dict()

    @staticmethod
    async def get_sensors_data_skeleton(
            session: AsyncSession,
            ecosystem: Ecosystem,
            time_window: timeWindow,
            level: ot.LEVELS | list[ot.LEVELS] | None = None,
    ) -> dict:
        level = level or "all"

        @cached(cache_sensors_data_skeleton)
        async def inner_func(
                ecosystem_id: str,
                time_window: timeWindow,
                level: list[ot.LEVELS],
        ) -> list:
            stmt = (
                select(Hardware).join(SensorHistory.sensor)
                .filter(Hardware.level.in_(level))
                .filter(Hardware.ecosystem_uid == ecosystem_id)
                .filter((SensorHistory.datetime > time_window.start) &
                        (SensorHistory.datetime <= time_window.end))
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
            level: ot.LEVELS | list[ot.LEVELS] | None = None,
            hardware_type: ot.TYPES | list[ot.TYPES] | None = None
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


# ---------------------------------------------------------------------------
#   Environmental parameters-related APIs
# ---------------------------------------------------------------------------
class environmental_parameter:
    # TODO: make gaia calls
    @staticmethod
    async def create(
            session: AsyncSession,
            parameters_info: dict,
    ) -> EnvironmentParameter:
        return await _create_entry(session, EnvironmentParameter, parameters_info)

    @staticmethod
    async def update(
            session: AsyncSession,
            parameter_info: dict,
            uid: str | None = None,
            parameter: str | None = None,

    ) -> None:
        parameter_info = parameter_info or {}
        uid = uid or parameter_info.pop("uid", None)
        parameter = parameter or parameter_info.pop("parameter", None)
        if not (uid or parameter):
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

    @staticmethod
    async def delete(
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
            uid: str | None = None,
            parameter: str | None = None,
            parameter_info: dict | None = None,
    ) -> EnvironmentParameter:
        parameter_info = parameter_info or {}
        uid = uid or parameter_info.pop("uid", None)
        parameter = parameter or parameter_info.pop("parameter", None)
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
            await environmental_parameter.update(
                session, parameter_info, uid
            )
        return environment_parameter


# ---------------------------------------------------------------------------
#   Hardware-related APIs
# ---------------------------------------------------------------------------
class hardware:
    @staticmethod
    async def create(
            session: AsyncSession,
            hardware_dict: dict,
    ) -> Hardware:
        return await _create_entry(session, Hardware, hardware_dict)

    @staticmethod
    async def update(
            session: AsyncSession,
            hardware_info: dict,
            uid: str | None,
    ) -> None:
        await _update_entry(session, Hardware, hardware_info, uid)

    @staticmethod
    async def delete(
            session: AsyncSession,
            uid: str,
    ) -> None:
        await _delete_entry(session, Hardware, uid)

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
            levels: ot.LEVELS | list[ot.LEVELS] | None = None,
            types: ot.TYPES | list[ot.TYPES] | None = None,
            models: str | list | None = None,
    ):
        query = select(Hardware)
        if hardware_uid is not None and "all" not in hardware_uid:
            if isinstance(hardware_uid, str):
                hardware_uid = hardware_uid.split(",")
            query = query.where(Hardware.uid.in_(hardware_uid))
        if ecosystem_uid is not None and "all" not in ecosystem_uid:
            if isinstance(ecosystem_uid, str):
                ecosystem_uid = ecosystem_uid.split(",")
            query = query.where(Hardware.ecosystem_uid.in_(ecosystem_uid))
        if levels is not None and "all" not in levels:
            if isinstance(levels, str):
                levels = levels.split(",")
            query = query.where(Hardware.level.in_(levels))
        if types is not None and "all" not in types:
            if isinstance(types, str):
                types = types.split(",")
            query = query.where(Hardware.type.in_(types))
        if models is not None and "all" not in models:
            if isinstance(models, str):
                models = models.split(",")
            query = query.where(Hardware.model.in_(models))
        return query

    @staticmethod
    async def get_multiple(
            session: AsyncSession,
            hardware_uids: str | list | None= None,
            ecosystem_uids: str | list | None = None,
            levels: ot.LEVELS | list[ot.LEVELS] | None = None,
            types: ot.TYPES | list[ot.TYPES] | None = None,
            models: str | list | None = None,
    ) -> list[Hardware]:
        stmt = hardware._get_query(
            hardware_uids, ecosystem_uids, levels, types, models
        )
        result = await session.execute(stmt)
        return result.unique().scalars().all()

    @staticmethod
    async def update_or_create(
            session: AsyncSession,
            hardware_info: dict | None = None,
            uid: str | None = None,
    ) -> Hardware:
        hardware_info = hardware_info or {}
        uid = uid or hardware_info.pop("uid", None)
        if not uid:
            raise ValueError(
                "Provide uid either as an argument or as a key in the updated info"
            )
        hardware_ = await hardware.get(session, uid)
        if not hardware_:
            hardware_info["uid"] = uid
            measures = hardware_info.pop("measure", [])
            if measures:
                if isinstance(measures, str):
                    measures = [measures]
                measures_ = measure.get_multiple(session, measures)
                if measures_:
                    hardware_info["measure"] = measures_
            hardware_ = await hardware.create(session, hardware_info)
        elif hardware_info:
            await hardware.update(session, hardware_info, uid)
        return hardware_

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
                    (SensorHistory.datetime > time_window.start) &
                    (SensorHistory.datetime <= time_window.end)
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
            levels: ot.LEVELS | list[ot.LEVELS] | None = None,
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
                    (SensorHistory.datetime > time_window.start) &
                    (SensorHistory.datetime <= time_window.end)
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
                select(SensorHistory.datetime, SensorHistory.value)
                .filter(SensorHistory.measure == measure)
                .filter(SensorHistory.sensor_uid == sensor_obj.uid)
                .filter((SensorHistory.datetime > time_window[0]) &
                        (SensorHistory.datetime <= time_window[1]))
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
            measures = [measure_.name for measure_ in sensor_obj.measure]
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
                measures = [measure_.name for measure_ in sensor_obj.measure]
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
    def get_current_data():
        cache = get_cache("sensors_data")
        return {**cache}

    @staticmethod
    def clear_current_data(key: str | None = None) -> None:
        cache = get_cache("sensors_data")
        if key:
            del cache[key]
        else:
            cache.clear()

    @staticmethod
    def update_current_data(data: dict):
        cache = get_cache("sensors_data")
        cache.update(data)

    @staticmethod
    async def create_record(
            session: AsyncSession,
            sensor_data: dict,
    ) -> SensorHistory:
        sensor_history = SensorHistory(**sensor_data)
        session.add(sensor_history)
        return sensor_history


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
    # TODO: cache?
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
class light:
    @staticmethod
    async def create(
            session: AsyncSession,
            light_data: dict,
    ) -> Light:
        light = Light(**light_data)
        session.add(light)
        return light

    @staticmethod
    async def update(
            session: AsyncSession,
            light_info: dict,
            ecosystem_uid: str | None = None,
    ) -> None:
        # TODO: call GAIA
        ecosystem_uid = ecosystem_uid or light_info.pop("ecosystem_uid", None)
        if not ecosystem_uid:
            raise ValueError(
                "Provide uid either as a parameter or as a key in the updated info"
            )
        stmt = (
            update(Light)
            .where(Light.ecosystem_uid == ecosystem_uid)
            .values(**light_info)
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
    async def update_or_create(
            session: AsyncSession,
            light_info: dict | None = None,
            ecosystem_uid: str | None = None,
    ) -> Light:
        light_info = light_info or {}
        ecosystem_uid = ecosystem_uid or light_info.pop("ecosystem_uid", None)
        if not ecosystem_uid:
            raise ValueError(
                "Provide uid either as an argument or as a key in the updated info"
            )
        light_ = await light.get(session, ecosystem_uid)
        if not light_:
            light_info["ecosystem_uid"] = ecosystem_uid
            light_ = await light.create(session, light_info)
        elif light_info:
            await light.update(session, light_info, ecosystem_uid)
        return light_


# ---------------------------------------------------------------------------
#   Health-related APIs
# ---------------------------------------------------------------------------
class health:
    @staticmethod
    async def create_record(
            session: AsyncSession,
            health_data: dict,
    ) -> Health:
        health = Health(**health_data)
        session.add(health)
        return health


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
