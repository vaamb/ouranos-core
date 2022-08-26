from collections import namedtuple
from statistics import mean
from typing import Union

from cachetools import cached, TTLCache
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.exceptions import NoEcosystemFound, WrongDataFormat
from src.api.utils import time_limits, timeWindow, create_time_window
from src.consts import HARDWARE_AVAILABLE, HARDWARE_TYPE
from src.cache import sensorsData
from src.database.models.gaia import (
    Ecosystem, Engine, Hardware, Measure, SensorHistory
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
        engines: Union[str, tuple, list] = "all",
) -> list[Engine]:
    if engines is None:
        engines = "all"
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


def get_engine_info(session: AsyncSession, engine: Engine) -> dict:
    return engine.to_dict()


def get_ecosystem_ids(session: AsyncSession, ecosystem: str) -> ecosystemIds:
    query = (
        select(Ecosystem)
        .where(
            (Ecosystem.uid == ecosystem) |
            (Ecosystem.name == ecosystem)
        )
    )
    ecosystem = session.execute(query).first()
    if ecosystem:
        return ecosystemIds(ecosystem.uid, ecosystem.name)
    raise NoEcosystemFound


async def get_ecosystems(
        session: AsyncSession,
        ecosystems: Union[str, tuple, list] = "all",
) -> list[Ecosystem]:
    if ecosystems is None:
        ecosystems = "all"
    if isinstance(ecosystems, str):
        ecosystems = ecosystems.split(",")
    if "all" in ecosystems:
        query = (
            select(Ecosystem)
                .order_by(Ecosystem.name.asc(),
                          Ecosystem.last_seen.desc())
        )
    elif "recent" in ecosystems:
        time_limit = time_limits()["recent"]

        query = (
            select(Ecosystem)
                .where(Ecosystem.last_seen >= time_limit)
                .order_by(Ecosystem.status.desc(),
                          Ecosystem.name.asc())
        )
    elif "connected" in ecosystems:
        query = (
            select(Ecosystem)
                .join(Engine.ecosystems)
                .where(Engine.connected)
                .order_by(Ecosystem.name.asc())
        )
    else:
        query = (
            select(Ecosystem)
                .join(Engine)
                .where(Ecosystem.uid.in_(ecosystems) |
                       Ecosystem.name.in_(ecosystems))
                .order_by(Ecosystem.last_seen.desc(),
                          Ecosystem.name.asc())
        )
    result = await session.execute(query)
    return result.scalars().all()


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


# TODO: delete
def summarize_ecosystems_management(session: AsyncSession,
                                    ecosystems_info: list) -> dict:
    limits = time_limits()
    return {
        "env_sensors": [
            ecosystemIds(ecosystem["uid"], ecosystem["name"])._asdict()
            for ecosystem in ecosystems_info
            if bool(
                session.query(Hardware)
                    .filter_by(ecosystem_id=ecosystem["uid"])
                    .filter_by(type="sensor", level="environment")
                    .filter(Hardware.last_log >= limits["sensors"])
                    .first()
            )
        ],
        "plant_sensors": [
            ecosystemIds(ecosystem["uid"], ecosystem["name"])._asdict()
            for ecosystem in ecosystems_info
            if bool(
                session.query(Hardware)
                    .filter_by(ecosystem_id=ecosystem["uid"])
                    .filter_by(type="sensor", level="plants")
                    .filter(Hardware.last_log >= limits["sensors"])
                    .first()
            )
        ],
        # TODO: check that we have valid lighting times
        "light": [
            ecosystemIds(ecosystem["uid"], ecosystem["name"])._asdict()
            for ecosystem in ecosystems_info if ecosystem["light"]
        ],
        "climate": [
            ecosystemIds(ecosystem["uid"], ecosystem["name"])._asdict()
            for ecosystem in ecosystems_info if ecosystem["climate"]
        ],
        "watering": [
            ecosystemIds(ecosystem["uid"], ecosystem["name"])._asdict()
            for ecosystem in ecosystems_info if ecosystem["watering"]
        ],
        "health": [
            ecosystemIds(ecosystem["uid"], ecosystem["name"])._asdict()
            for ecosystem in ecosystems_info if ecosystem["health"]
        ],
        "alarms": [
            ecosystemIds(ecosystem["uid"], ecosystem["name"])._asdict()
            for ecosystem in ecosystems_info if ecosystem["alarms"]
        ],
        "webcam": [
            ecosystemIds(ecosystem["uid"], ecosystem["name"])._asdict()
            for ecosystem in ecosystems_info if ecosystem["webcam"]
        ],
        "switches": [
            ecosystemIds(ecosystem["uid"], ecosystem["name"])._asdict()
            for ecosystem in ecosystems_info if ecosystem["switches"]
        ],
        "recent": [
            ecosystemIds(ecosystem["uid"], ecosystem["name"])._asdict()
            for ecosystem in ecosystems_info
        ],
    }


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


def get_ecosystem_sensors_data_skeleton(
        session: AsyncSession,
        ecosystem: Ecosystem,
        time_window: timeWindow,
        level: Union[str, tuple, list] = "all",
) -> dict:
    if level is None:
        level = "all"
    @cached(cache_sensors_data_skeleton)
    def inner_func(
            session: AsyncSession,
            ecosystem_id: str,
            time_window: timeWindow,
            level: Union[str, list, tuple],
    ) -> list:
        # TODO: use a function for level and
        sensors = (
            session.query(Hardware).join(SensorHistory.sensor)
                .filter(Hardware.level.in_(level))
                .filter(SensorHistory.ecosystem_uid == ecosystem_id)
                .filter((SensorHistory.datetime > time_window[0]) &
                        (SensorHistory.datetime <= time_window[1]))
                .all()
        )
        temp = {}
        for sensor in sensors:
            for measure in sensor.measure:
                try:
                    temp[measure.name][sensor.uid] = sensor.name
                except KeyError:
                    temp[measure.name] = {sensor.uid: sensor.name}
        order = ["temperature", "humidity", "lux", "dew_point",
                 "absolute_moisture",
                 "moisture"]
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
        "sensors_skeleton": inner_func(
            session=session, ecosystem_id=ecosystem.uid,
            time_window=time_window, level=level)
    }


def _get_hardware_query(
        hardware_uids: Union[str, tuple, list] = "all",
        ecosystem_uids: Union[str, tuple, list] = "all",
        levels: Union[str, tuple, list] = "all",
        types: Union[str, tuple, list] = "all",
        models: Union[str, tuple, list] = "all",
):
    query = select(Hardware)
    if "all" not in hardware_uids:
        if isinstance(hardware_uids, str):
            hardware_uids = hardware_uids.split(",")
        query = query.where(Hardware.uid.in_(hardware_uids))
    if "all" not in ecosystem_uids:
        if isinstance(ecosystem_uids, str):
            ecosystem_uids = ecosystem_uids.split(",")
        query = query.where(Hardware.ecosystem_uid.in_(ecosystem_uids))
    if "all" not in levels:
        if isinstance(levels, str):
            level = levels.split(",")
        query = query.where(Hardware.level.in_(levels))
    if "all" not in types:
        if isinstance(types, str):
            types = types.split(",")
        query = query.where(Hardware.type.in_(types))
    if "all" not in models:
        if isinstance(models, str):
            models = models.split(",")
        query = query.where(Hardware.model.in_(models))
    return query


def get_hardware(
        session: AsyncSession,
        hardware_uids: Union[str, tuple, list] = "all",
        ecosystem_uids: Union[str, tuple, list] = "all",
        levels: Union[str, tuple, list] = "all",
        types: Union[str, tuple, list] = "all",
        models: Union[str, tuple, list] = "all",
) -> list[Hardware]:
    query = _get_hardware_query(
        hardware_uids,ecosystem_uids, levels, types, models
    )
    return session.execute(query).scalars().all()


def get_sensors(
        session: AsyncSession,
        hardware_uids: Union[str, tuple, list] = "all",
        ecosystem_uids: Union[str, tuple, list] = "all",
        levels: Union[str, tuple, list] = "all",
        models: Union[str, tuple, list] = "all",
        time_window: timeWindow = None,
) -> list[Hardware]:
    query = _get_hardware_query(
        hardware_uids, ecosystem_uids, levels, "sensor", models
    )
    if time_window:
        query = (
            query.join(SensorHistory.sensor)
                .where(
                    (SensorHistory.datetime > time_window.start) &
                    (SensorHistory.datetime <= time_window.end)
                )
                .distinct()
        )
    return session.execute(query).scalars().all()


def get_hardware_info(
        session: AsyncSession,
        hardware: Hardware
) -> dict:
    return hardware.to_dict()


# TODO: cache?
def _get_measure_unit(session: AsyncSession, measure_name: str) -> str:
    return (
        session.query(Measure)
            .filter(Measure.name == measure_name)
            .first()
            .unit
    )


def _get_historic_sensor_data_record(
        session: AsyncSession,
        sensor_obj: Hardware,
        measure: str,
        time_window: timeWindow
) -> list:
    @cached(cache_sensors_data_raw)
    def cached_func(
            sensor_obj: Hardware,
            measure: str,
            time_window: timeWindow
    ) -> list:
        return (
            session.query(SensorHistory)
                .filter(SensorHistory.measure == measure)
                .filter(SensorHistory.sensor_uid == sensor_obj.uid)
                .filter((SensorHistory.datetime > time_window[0]) &
                        (SensorHistory.datetime <= time_window[1]))
                .with_entities(SensorHistory.datetime, SensorHistory.value)
                .all()
        )
    return cached_func(sensor_obj, measure, time_window)


def _get_historic_sensors_data(
        session: AsyncSession,
        sensor_obj: Hardware,
        measures: Union[str, tuple, list],
        time_window: timeWindow,
) -> list:
    if "all" in measures:
        measures = [measure.name for measure in sensor_obj.measure]
    elif isinstance(measures, str):
        measures = measures.split(",")
    rv = []
    for measure in measures:
        records = _get_historic_sensor_data_record(
            session, sensor_obj, measure, time_window
        )
        if records:
            rv.append({
                "measure": measure,
                "unit": _get_measure_unit(session, measure),
                "records": records,
            })
    return rv


def _get_current_sensors_data(
        session: AsyncSession,
        sensor_obj: Hardware,
        measures: Union[str, tuple, list],
) -> list:
    try:
        ecosystem_uid = sensor_obj.ecosystem_uid
        ecosystem = sensorsData[ecosystem_uid]
        if "all" in measures:
            measures = [measure.name for measure in sensor_obj.measure]
        elif isinstance(measures, str):
            measures = measures.split(",")
        rv = []
        for measure in measures:
            value = ecosystem["data"].get(sensor_obj.uid, {}).get(measure, None)
            if value:
                rv.append({
                    "measure": measure,
                    "unit": _get_measure_unit(session, measure),
                    "value": value,
                })
        return rv
    except KeyError:
        return []


def get_sensor_info(
        session: AsyncSession,
        sensor: Hardware,
        measures: Union[str, tuple, list] = "all",
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
            data = _get_historic_sensors_data(
                session, sensor, measures, time_window
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


# TODO: rewrite or delete
def _get_ecosystem_historic_sensors_data(
        session: AsyncSession,
        ecosystem: Ecosystem,
        time_window: timeWindow,
        level: Union[str, tuple, list] = "all",
) -> dict:
    if "all" in level:
        level = ["environment", "plants"]
    elif isinstance(level, str):
        level = level.split(",")

    return {
        "uid": ecosystem.uid,
        "time_window": {
            "start": time_window.start,
            "end": time_window.end,
        },
        "level": level,
        "data": get_data(ecosystem.uid, level, time_window),
    }


def average_historic_sensors_data(sensors_data: dict,
                                  precision: int = 2) -> dict:
    # Dummy function to allow memoization
    # @cached(cache_sensors_data_average)
    def average_data(ecosystem, time_window):
        summary = {
            "name": sensors_data[ecosystem]["name"],
            "time_window": time_window,
            "data": {}
        }
        for measure in sensors_data[ecosystem]["data"]:
            summary["data"][measure] = {}
            for sensor in sensors_data[ecosystem]["data"][measure]:
                data = sensors_data[ecosystem]["data"][measure][sensor]
                summary["data"][measure][sensor] = {
                    "name": data["name"],
                    "value": round(mean([i[1] for i in data["values"]]),
                                   precision)
                }
        return summary

    return {ecosystem: average_data(ecosystem,
                                    sensors_data[ecosystem]["time_window"])
            for ecosystem in sensors_data}


def summarize_sensors_data(sensors_data: dict, precision: int = 2) -> dict:
    # Dummy function to allow memoization
    # @cached(cache_sensors_data_summary)
    def summarize_data(ecosystem, datatype: str = "historic"):
        data = sensors_data[ecosystem]["data"]
        values = {}
        means = {}
        for measure in data:
            values[measure] = []
            for sensor in data[measure]:
                values[measure].append(data[measure][sensor]["value"])
        for measure in values:
            means[measure] = round(mean(values[measure]), precision)
        result = {
            "name": sensors_data[ecosystem]["name"],
            "data": means
        }
        try:
            result["datetime"] = sensors_data[ecosystem]["datetime"]
        except KeyError:
            result["time_window"] = sensors_data[ecosystem]["time_window"]
        return result

    summarized_data = {}
    for ecosystem in sensors_data:
        datatype = "current"
        if sensors_data[ecosystem].get("time_window"):
            datatype = "historic"
        summarized_data[ecosystem] = summarize_data(ecosystem, datatype)
    return summarized_data


# ---------------------------------------------------------------------------
#   Hardware-related APIs
# ---------------------------------------------------------------------------
def get_hardware_models_available() -> list:
    return HARDWARE_AVAILABLE


def create_hardware():
    # TODO
    pass


def update_hardware(
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
        session.execute(query)
    except KeyError:
        raise WrongDataFormat(
            "hardware_dict should have the following keys: 'name', 'type', "
            "'level', 'model', 'address'"
        )


def delete_hardware(
        session: AsyncSession,
        hardware_uid: str,
) -> None:
    query = delete(Hardware).where(Hardware.uid == hardware_uid)
    session.execute(query)


def get_ecosystems_hardware(
        session: AsyncSession,
        ecosystems_query_obj: list[Ecosystem],
        level: Union[str, tuple, list] = "all",
        hardware_type: Union[str, tuple, list] = "all"
) -> list[dict]:
    if "all" in level:
        level = ("environment", "plants")
    if "all" in hardware_type:
        hardware_type = HARDWARE_TYPE
    elif "actuators" in hardware_type:
        hardware_type = HARDWARE_TYPE.remove("sensor")

    return [{
        "ecosystem_uid": ecosystem.uid,
        "ecosystem_name": ecosystem.name,
        "hardware": [hardware.to_dict() for hardware in (
            session.query(Hardware).join(Ecosystem)
                .filter(Ecosystem.uid == ecosystem.uid)
                .filter(Hardware.type.in_(hardware_type))
                .filter(Hardware.level.in_(level))
                .order_by(Hardware.type)
                .order_by(Hardware.level)
                .all()
        )]
    } for ecosystem in ecosystems_query_obj]


def get_plants(
        session: AsyncSession,
        ecosystems_query_obj: list[Ecosystem],
) -> list[dict[str, Union[str, list[dict[str, str]]]]]:
    return [{
        "ecosystem_uid": ecosystem.uid,
        "ecosystem_name": ecosystem.name,
        "plants": [
            plant.to_dict()
            for plant in ecosystem.plants
        ]
    } for ecosystem in ecosystems_query_obj]


def get_measures(session: AsyncSession) -> list:
    return [measure.to_dict() for measure in session.query(Measure).all()]
