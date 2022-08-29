from __future__ import annotations

from collections import namedtuple
import typing as t

from cachetools import cached, TTLCache
import cachetools.func
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.exceptions import NoEcosystemFound, WrongDataFormat
from src.api.utils import time_limits, timeWindow, create_time_window
from src.consts import HARDWARE_AVAILABLE, HARDWARE_TYPE
from src.cache import sensorsData
from src.database.models.gaia import (
    Ecosystem, Engine, GaiaWarning, Hardware, Measure, SensorHistory
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


async def get_engines(
        session: AsyncSession,
        engines: t.Optional[str | tuple | list] = None,
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


async def get_engine(
        session: AsyncSession,
        engine_id: str,
) -> Engine:
    stmt = (
        select(Engine)
        .where((Engine.uid == engine_id) | (Engine.sid == engine_id))
    )
    result = await session.execute(stmt)
    return result.scalars().one_or_none()


def get_engine_info(session: AsyncSession, engine: Engine) -> dict:
    return engine.to_dict()


async def get_ecosystem_ids(session: AsyncSession, ecosystem: str) -> ecosystemIds:
    stmt = (
        select(Ecosystem)
        .where(
            (Ecosystem.uid == ecosystem) |
            (Ecosystem.name == ecosystem)
        )
    )
    result = await session.execute(stmt)
    ecosystem = result.first()
    if ecosystem:
        return ecosystemIds(ecosystem.uid, ecosystem.name)
    raise NoEcosystemFound


async def create_ecosystem(
        session: AsyncSession,
        ecosystem_info: dict,
):
    ecosystem = Ecosystem(**ecosystem_info)
    session.add(ecosystem)
    await session.commit()
    return ecosystem


async def get_ecosystems(
        session: AsyncSession,
        ecosystems: t.Optional[str | tuple | list] = None,
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
    return result.scalars().all()


async def get_ecosystem(
        session: AsyncSession,
        ecosystem_id: str,
) -> Ecosystem:
    ecosystem_id = (ecosystem_id, )
    stmt = (
        select(Ecosystem)
        .where(Ecosystem.uid.in_(ecosystem_id) | Ecosystem.name.in_(ecosystem_id))
    )
    result = await session.execute(stmt)
    return result.scalars().one_or_none()


def get_ecosystem_info(session: AsyncSession, ecosystem: Ecosystem) -> dict:
    return ecosystem.to_dict()


def get_ecosystem_management(
        session: AsyncSession,
        ecosystem: Ecosystem,
) -> dict:
    limits = time_limits()

    @cached(cache_ecosystem_info)
    def cached_func(ecosystem: Ecosystem):
        management = ecosystem.management_dict()
        return {
            "uid": ecosystem.uid,
            "name": ecosystem.name,
            "sensors": management["sensors"],
            "light": management["light"],
            "climate": management["climate"],
            "watering": management["watering"],
            "health": management["health"],
            "alarms": management["alarms"],
            "webcam": management["webcam"],
            "switches": any((management["climate"], management["light"])),
            "environment_data": bool(
                ecosystem.hardware
                    .where(
                        Hardware.type == "sensor",
                        Hardware.level == "environment"
                    )
                    .filter(Hardware.last_log >= limits["sensors"])
                    .first()
            ),
            "plants_data": bool(
                ecosystem.hardware
                    .where(
                        Hardware.type == "sensor",
                        Hardware.level == "plants"
                    )
                    .filter(Hardware.last_log >= limits["sensors"])
                    .first()
            ),
        }
    return cached_func(ecosystem)


def get_light_info(session: AsyncSession, ecosystem: Ecosystem) -> dict:
    return ecosystem.light.first().to_dict()


def get_environmental_parameters(
        session: AsyncSession,
        ecosystem: Ecosystem,
) -> dict:
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


async def get_ecosystem_sensors_data_skeleton(
        session: AsyncSession,
        ecosystem: Ecosystem,
        time_window: timeWindow,
        level: t.Optional[str | tuple | list] = None,
) -> dict:
    level = level or "all"
    @cached(cache_sensors_data_skeleton)
    async def inner_func(
            ecosystem_id: str,
            time_window: timeWindow,
            level: t.Optional[str | tuple | list] = None,
    ) -> list:
        # TODO: use a function for level and
        stmt = (
            select(Hardware).join(SensorHistory.sensor)
            .filter(Hardware.level.in_(level))
            .filter(SensorHistory.ecosystem_uid == ecosystem_id)
            .filter((SensorHistory.datetime > time_window[0]) &
                    (SensorHistory.datetime <= time_window[1]))
        )
        result = await session.execute(stmt)
        sensors = result.scalars().all()
        temp = {}
        for sensor in sensors:
            for measure in sensor.measure:
                try:
                    temp[measure.name][sensor.uid] = sensor.name
                except KeyError:
                    temp[measure.name] = {sensor.uid: sensor.name}
        order = [
            "temperature", "humidity", "lux", "dew_point", "absolute_moisture",
            "moisture"
        ]
        return [{
            "measure": measure,
            "sensors": [{
                "uid": sensor,
                "name": temp[measure][sensor]
            } for sensor in temp[measure]]
        } for measure in {
            key: temp[key] for key in order if temp.get(key)
        }]

    if "all" in level:
        level = ("environment", "plants")
    elif isinstance(level, str):
        level = level.split(",")
    return {
        "uid": ecosystem.uid,
        "name": ecosystem.name,
        "level": level,
        "sensors_skeleton": await inner_func(
            session=session, ecosystem_id=ecosystem.uid,
            time_window=time_window, level=level)
    }


# ---------------------------------------------------------------------------
#   Hardware-related APIs
# ---------------------------------------------------------------------------
def create_hardware(
        session: AsyncSession,
        hardware_dict: dict,
):
    hardware_dict.pop("uid")
    # TODO: need to call gaia


def _get_hardware_query(
        hardware_uids: t.Optional[str | tuple | list] = None,
        ecosystem_uids: t.Optional[str | tuple | list] = None,
        levels: t.Optional[str | tuple | list] = None,
        types: t.Optional[str | tuple | list] = None,
        models: t.Optional[str | tuple | list] = None,
):
    query = select(Hardware)
    if hardware_uids is not None and "all" not in hardware_uids:
        if isinstance(hardware_uids, str):
            hardware_uids = hardware_uids.split(",")
        query = query.where(Hardware.uid.in_(hardware_uids))
    if ecosystem_uids is not None and "all" not in ecosystem_uids:
        if isinstance(ecosystem_uids, str):
            ecosystem_uids = ecosystem_uids.split(",")
        query = query.where(Hardware.ecosystem_uid.in_(ecosystem_uids))
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


async def get_hardware(
        session: AsyncSession,
        hardware_uids: t.Optional[str | tuple | list] = None,
        ecosystem_uids: t.Optional[str | tuple | list] = None,
        levels: t.Optional[str | tuple | list] = None,
        types: t.Optional[str | tuple | list] = None,
        models: t.Optional[str | tuple | list] = None,
) -> list[Hardware]:
    stmt = _get_hardware_query(
        hardware_uids, ecosystem_uids, levels, types, models
    )
    result = await session.execute(stmt)
    return result.scalars().all()


async def update_hardware(
        session: AsyncSession,
        hardware_uid: str,
        hardware_dict: dict[str]
) -> None:
    try:
        hardware_dict.pop("uid", None)
        query = (
            update(Hardware)
            .where(Hardware.uid == hardware_uid)
            .values(**hardware_dict)
        )
        await session.execute(query)
    except KeyError:
        raise WrongDataFormat(
            "hardware_dict should have the following keys: 'name', 'type', "
            "'level', 'model', 'address'"
        )


async def delete_hardware(
        session: AsyncSession,
        hardware_uid: str,
) -> None:
    query = delete(Hardware).where(Hardware.uid == hardware_uid)
    await session.execute(query)


def get_hardware_info(
        session: AsyncSession,
        hardware: Hardware
) -> dict:
    return hardware.to_dict()


def get_hardware_models_available() -> list:
    return HARDWARE_AVAILABLE


async def get_sensors(
        session: AsyncSession,
        hardware_uids: t.Optional[str | tuple | list] = None,
        ecosystem_uids: t.Optional[str | tuple | list] = None,
        levels: t.Optional[str | tuple | list] = None,
        models: t.Optional[str | tuple | list] = None,
        time_window: timeWindow = None,
) -> list[Hardware]:
    stmt = _get_hardware_query(
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
    return result.scalars().all()


# TODO: cache?
async def _get_measure_unit(session: AsyncSession, measure_name: str) -> str:
    stmt = (
        select(Measure)
        .filter(Measure.name == measure_name)
    )
    result = await session.execute(stmt)
    return result.scalars().first().unit


async def _get_historic_sensor_data_record(
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
            select(SensorHistory)
            .filter(SensorHistory.measure == measure)
            .filter(SensorHistory.sensor_uid == sensor_obj.uid)
            .filter((SensorHistory.datetime > time_window[0]) &
                    (SensorHistory.datetime <= time_window[1]))
            .with_entities(SensorHistory.datetime, SensorHistory.value)
        )
        result = await session.execute(stmt)
        return result.scalars().all()
    return await cached_func(sensor_obj, measure, time_window)


async def _get_historic_sensors_data(
        session: AsyncSession,
        sensor_obj: Hardware,
        time_window: timeWindow,
        measures: t.Optional[str | tuple | list] = None,
) -> list:
    if measures is None or "all" in measures:
        measures = [measure.name for measure in sensor_obj.measure]
    elif isinstance(measures, str):
        measures = measures.split(",")
    rv = []
    for measure in measures:
        records = await _get_historic_sensor_data_record(
            session, sensor_obj, measure, time_window
        )
        if records:
            rv.append({
                "measure": measure,
                "unit": await _get_measure_unit(session, measure),
                "records": records,
            })
    return rv


async def _get_current_sensors_data(
        session: AsyncSession,
        sensor_obj: Hardware,
        measures: t.Optional[str | tuple | list] = None,
) -> list:
    try:
        ecosystem_uid = sensor_obj.ecosystem_uid
        ecosystem = sensorsData[ecosystem_uid]
        if measures is None or "all" in measures:
            measures = [measure.name for measure in sensor_obj.measure]
        elif isinstance(measures, str):
            measures = measures.split(",")
        rv = []
        for measure in measures:
            value = ecosystem["data"].get(sensor_obj.uid, {}).get(measure, None)
            if value:
                rv.append({
                    "measure": measure,
                    "unit": await _get_measure_unit(session, measure),
                    "value": value,
                })
        return rv
    except KeyError:
        return []


async def get_sensor_info(
        session: AsyncSession,
        sensor: Hardware,
        measures: t.Optional[str | tuple | list] = None,
        current_data: bool = True,
        historic_data: bool = True,
        time_window: timeWindow = None,
) -> dict:
    rv = sensor.to_dict()
    if current_data or historic_data:
        rv.update({"data": {}})
        if current_data:
            data = _get_current_sensors_data(session, sensor, measures)
            if data:
                rv["data"].update({
                    "current": {
                        "timestamp": sensorsData[sensor.ecosystem_uid]["datetime"],
                        "data": data,
                    }
                })
            else:
                rv["data"].update({"current": None})
        if historic_data:
            if not time_window:
                time_window = create_time_window()
            data = await _get_historic_sensors_data(
                session, sensor, time_window, measures
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


async def get_ecosystems_hardware(
        session: AsyncSession,
        ecosystems_query_obj: list[Ecosystem],
        level: t.Optional[str | tuple | list] = None,
        hardware_type: t.Optional[str | tuple | list] = None
) -> list[dict]:
    if level is None or "all" in level:
        level = ("environment", "plants")
    if hardware_type is None or "all" in hardware_type:
        hardware_type = HARDWARE_TYPE
    elif "actuators" in hardware_type:
        hardware_type = HARDWARE_TYPE.remove("sensor")

    rv = []
    for ecosystem in ecosystems_query_obj:
        stmt = (
            select(Hardware).join(Ecosystem)
            .filter(Ecosystem.uid == ecosystem.uid)
            .filter(Hardware.type.in_(hardware_type))
            .filter(Hardware.level.in_(level))
            .order_by(Hardware.type)
            .order_by(Hardware.level)
        )
        result = await session.execute(stmt)

        rv.append({
            "ecosystem_uid": ecosystem.uid,
            "ecosystem_name": ecosystem.name,
            "hardware": [hardware.to_dict() for hardware in result.scalars().all()]
        })
    return rv


async def get_measures(session: AsyncSession) -> list:
    stmt = select(Measure)
    result = await session.execute(stmt)
    return [measure.to_dict() for measure in result.scalars().all()]


def get_plants(
        session: AsyncSession,
        ecosystems_query_obj: list[Ecosystem],
) -> list[dict[str, [str | list[dict[str, str]]]]]:
    return [{
        "ecosystem_uid": ecosystem.uid,
        "ecosystem_name": ecosystem.name,
        "plants": [
            plant.to_dict()
            for plant in ecosystem.plants
        ]
    } for ecosystem in ecosystems_query_obj]


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
        .order_by(GaiaWarning.level.desc())
        .order_by(GaiaWarning.id)
        .with_entities(
            GaiaWarning.created, GaiaWarning.emergency, GaiaWarning.title
        )
        .limit(limit)
    )
    result = await session.execute(stmt)
    return result.scalars().all() or []
