from collections import namedtuple
from datetime import datetime
from typing import Union

from cachetools import cached, TTLCache
from numpy import mean
from sqlalchemy.orm.session import Session

from src.app.API.exceptions import NoEcosystemFound
from src.app.API.utils import time_limits, timeWindow
from src.dataspace import sensorsData
from src.models import Ecosystem, EngineManager, Hardware, Management, SensorData, Service

ALL_HARDWARE = ["sensor", "light", "heater", "cooler", "humidifier",
                "dehumidifier"]


# TODO: move this into config
max_ecosystems = 32

cache_ecosystem_info = TTLCache(maxsize=max_ecosystems, ttl=60)
cache_sensors_data_skeleton = TTLCache(maxsize=max_ecosystems, ttl=900)
cache_sensors_data_raw = TTLCache(maxsize=max_ecosystems * 32, ttl=900)
cache_sensors_data_average = TTLCache(maxsize=max_ecosystems, ttl=300)
cache_sensors_data_summary = TTLCache(maxsize=max_ecosystems * 2, ttl=300)


class ecosystemIds(namedtuple("ecosystemIds", ("uid", "name"))):
    __slots__ = ()


def get_managers_query_obj(session: Session,
                           managers: tuple = ()) -> list[EngineManager]:
    if managers:
        return (session.query(EngineManager)
                .filter((EngineManager.uid.in_(managers)) |
                        (EngineManager.sid.in_(managers)))
                .order_by(EngineManager.uid.asc())
                .order_by(EngineManager.last_seen.desc())
                .all())
    return (session.query(EngineManager)
            .order_by(EngineManager.uid.asc())
            .order_by(EngineManager.last_seen.desc())
            .all())


def get_connected_managers_query_obj(session: Session) -> list[EngineManager]:
    return (session.query(EngineManager)
            .filter(EngineManager.connected)
            .order_by(EngineManager.uid.asc())
            .all())


def get_recent_managers_query_obj(session: Session) -> list[EngineManager]:
    time_limit = time_limits()["recent"]
    return (session.query(EngineManager)
            .filter(EngineManager.last_seen >= time_limit)
            .order_by(EngineManager.uid.asc())
            .all())


def get_managers(session: Session, managers_qo: list[EngineManager]) -> list[
    dict]:
    return [manager.to_dict() for manager in managers_qo]


def get_ecosystem_ids(session: Session,
                      ecosystem: str
                      ) -> ecosystemIds:
    rv = (session.query(Ecosystem)
          .filter((Ecosystem.id == ecosystem) |
                  (Ecosystem.name == ecosystem))
          .first()
          )
    if rv:
        return ecosystemIds(rv.id, rv.name)
    raise NoEcosystemFound


def get_connected_ecosystems(session: Session) -> list:
    ecosystems = (session.query(Ecosystem).join(EngineManager)
                  .filter(EngineManager.connected)
                  .all())
    # TODO: change to list of dicts
    return [ecosystem.id for ecosystem in ecosystems]


def get_recent_ecosystems(session: Session, time_limit: datetime) -> list:
    ecosystems = (session.query(Ecosystem)
                  .filter(Ecosystem.last_seen >= time_limit)
                  .all())
    return [ecosystem.id for ecosystem in ecosystems]


def get_ecosystems_query_obj(session: Session,
                             ecosystems: Union[str, tuple, list] = "all",
                             ) -> list[Ecosystem]:
    if not ecosystems or "all" in ecosystems:  # TODO: add options for recent and connected
        return (session.query(Ecosystem)
                .order_by(Ecosystem.name.asc())
                .order_by(Ecosystem.last_seen.desc())
                .all())
    if "recent" in ecosystems:
        time_limit = time_limits()["recent"]
        return (session.query(Ecosystem)
                .filter(Ecosystem.last_seen >= time_limit)
                .order_by(Ecosystem.status.desc())
                .order_by(Ecosystem.name.asc())
                .all())
    if "connected" in ecosystems:
        return (session.query(Ecosystem).join(EngineManager)
                .filter(EngineManager.connected)
                .order_by(Ecosystem.name.asc())
                .all())
    if isinstance(ecosystems, str):
        ecosystems = (ecosystems,)
    return (session.query(Ecosystem).join(EngineManager)
            .filter((Ecosystem.id.in_(ecosystems)) |
                    (Ecosystem.name.in_(ecosystems)))
            .order_by(Ecosystem.last_seen.desc())
            .order_by(Ecosystem.name.asc())
            .all())


def get_ecosystems(session: Session,
                   ecosystems_query_obj: list[Ecosystem],
                   ) -> list[dict]:
    return [ecosystem.to_dict() for ecosystem in ecosystems_query_obj]


def get_ecosystems_management(session: Session,
                              ecosystems_query_obj: list[Ecosystem],
                              ) -> list[dict]:
    limits = time_limits()

    def get_management(ecosystem):
        # Dummy function to allow memoization
        @cached(cache_ecosystem_info)
        def cached_func(ecosystem_id):
            return {
                "uid": ecosystem.id,
                "name": ecosystem.name,
                "sensors": bool(
                    ecosystem.manages(Management["sensors"])
                ),
                "light": True if (
                        ecosystem.manages(Management["light"])
                        and ecosystem.hardware.filter_by(type="light").first()
                ) else False,
                "climate": True if (
                        ecosystem.manages(Management["climate"])
                        and ecosystem.hardware.filter(
                    ecosystem.hardware.type.in_(
                        "heater", "chiller", "cooler", "humidifier",
                        "dehumidifier")
                ).first()
                ) else False,
                "watering": True if (
                        ecosystem.manages(Management["watering"])
                        and ecosystem.hardware.filter_by(
                    type="watering").first()
                ) else False,
                "health": True if (
                        ecosystem.manages(Management["health"]) and
                        session.query(Hardware)
                        .filter_by(ecosystem_id=ecosystem.id)
                        .filter_by(type="camera")
                        .first()
                ) else False,
                "alarms": ecosystem.manages(Management["alarms"]),
                "webcam": (
                        ecosystem.manages(Management["webcam"]) and
                        session.query(Service)
                        .filter_by(name="webcam")
                        .first()
                        .status
                ),
                # TODO: use hardware func to check, check climate also
                "switches": True if ecosystem.hardware.filter_by(
                    type="light").first()  # TODO: add heater, humidifier ...
                                    and ecosystem.manages(Management["light"])
                                    and ecosystem.id in sensorsData else False,
            }

        return cached_func(ecosystem.id)

    return [get_management(ecosystem) for ecosystem in ecosystems_query_obj]


def summarize_ecosystems_management(session: Session,
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


def get_light_info(ecosystems_query_obj: list[Ecosystem]) -> list:
    return [
        ecosystem.light.first().to_dict() for ecosystem in ecosystems_query_obj
    ]


def get_environmental_parameters(session: Session,
                                 ecosystems_query_obj: list[Ecosystem],
                                 ) -> list:
    return [{
        "ecosystem_uid": ecosystem.id,
        "ecosystem_name": ecosystem.name,
        "environmental_parameters": [
            parameter.to_dict()
            for parameter in ecosystem.environment_parameters
        ]
    } for ecosystem in ecosystems_query_obj]


def get_current_sensors_data(session: Session,
                             ecosystems_query_obj: list[Ecosystem]) -> list:
    """ Get the current data for the given ecosystems

    Returns a dict with the current data for the given ecosystems if they exist
    and recently sent sensors data.
    """
    rv = []
    for ecosystem in ecosystems_query_obj:
        try:
            rv.append(sensorsData[ecosystem.id])
        except KeyError:
            pass
    return rv


def get_current_sensors_data_old(*ecosystems: str, session: Session) -> dict:
    # TODO: rename and use it to classify the result from get_current_sensors_data
    """ Get the current data for the given ecosystems

    Returns a dict with the current data for the given ecosystems if they exist
    and recently sent sensors data.
    """
    if not ecosystems:
        ecosystems = [uid for uid in sensorsData]
    data = {}
    for ecosystem in ecosystems:
        ids = get_ecosystem_ids(session, ecosystem)
        if ids:
            try:
                reorganized = {}
                for sensor in sensorsData[ids.uid]["data"]:
                    sensor_name = (session.query(Hardware)
                                   .filter(Hardware.id == sensor)
                                   .first()
                                   .name
                                   )
                    for measure in sensorsData[ids.uid]["data"][sensor]:
                        try:
                            reorganized[measure][sensor] = {
                                "name": sensor_name,
                                "value": sensorsData[ids.uid]["data"][
                                    sensor][measure]
                            }
                        except KeyError:
                            reorganized[measure] = {sensor: {
                                "name": sensor_name,
                                "value": sensorsData[ids.uid]["data"][
                                    sensor][measure]
                            }}
                data[ids.uid] = {
                    "name": ids.name,
                    "datetime": sensorsData[ids.uid]["datetime"],
                    "data": reorganized
                }
            except KeyError:
                pass
    return data


@cached(cache_sensors_data_skeleton)
def _get_sensors_data_skeleton(session: Session,
                               ecosystem_id: str,
                               time_window: timeWindow,
                               level: Union[str, tuple] = "all",
                               ) -> dict:
    if isinstance(level, str):
        if level == "all":
            level = ("environment", "plants")
        else:
            level = (level,)

    rv = {}
    # Don't use group_by: faster by 0.2 ms in real dataset
    subquery = (
        session.query(SensorData.sensor_id).join(Hardware)
            .filter(Hardware.level.in_(level))
            .filter(SensorData.ecosystem_id == ecosystem_id)
            .filter((SensorData.datetime > time_window[0]) &
                    (SensorData.datetime <= time_window[1]))
            .subquery()
    )

    sensors = (
        session.query(Hardware)
            .filter(Hardware.id.in_(subquery))
            .all()
    )

    for sensor in sensors:
        for measure in sensor.measure:
            try:
                rv[measure.name][sensor.id] = sensor.name
            except KeyError:
                rv[measure.name] = {sensor.id: sensor.name}
    return rv


def get_ecosystems_sensors_data_skeleton(session: Session,
                                         ecosystems_query_obj: list[Ecosystem],
                                         time_window: timeWindow,
                                         level: Union[
                                             str, tuple, list] = "all",
                                         ):
    if isinstance(level,
                  list):  # TODO: move to _get_sensors ... and cache an inner fct
        level = tuple(level)
    elif isinstance(level, str):
        level = (level,)
    return [{
        "ecosystem_uid": ecosystem.id,
        "name": ecosystem.name,
        "level": level,
        "sensors_skeleton": _get_sensors_data_skeleton(
            session=session, ecosystem_id=ecosystem.id,
            time_window=time_window, level=level)
    } for ecosystem in ecosystems_query_obj]


@cached(cache_sensors_data_raw)
def get_historic_sensor_data(session: Session,
                             sensor_uid: str,
                             measure: str,
                             time_window: timeWindow) -> list:
    values = (session.query(SensorData)
              .filter(SensorData.measure == measure)
              .filter(SensorData.sensor_id == sensor_uid)
              .filter((SensorData.datetime > time_window[0]) &
                      (SensorData.datetime <= time_window[1]))
              .with_entities(SensorData.datetime,
                             SensorData.value)
              .all()
              )
    return values


def get_historic_sensors_data_by_sensor(session: Session,
                                        sensor_uid: str,
                                        measures: Union[str, tuple, list],
                                        time_window: timeWindow) -> list:
    sensor = session.query(Hardware).filter(
        Hardware.id == sensor_uid).first()
    if "all" in measures:
        measures = [measure.name for measure in sensor.measure]
    elif isinstance(measures, str):
        measures = (measures,)

    if sensor:
        return [{
            "ecosystem_uid": sensor.ecosystem_id,
            "data": [{
                "sensor_uid": sensor_uid,
                # "name": sensor.name,
                # "level": sensor.level,
                # "type": sensor.type,
                # "model": sensor.model,
                "measures": [
                    {"name": measure,
                     "values": get_historic_sensor_data(
                         session, sensor_uid, measure, time_window)}
                    for measure in measures
                ]
            }]
        }]
    return []


def _fill_historic_sensors_data_skeleton(session: Session,
                                         time_window: timeWindow,
                                         data_skeleton: dict,
                                         ) -> dict:
    rv = data_skeleton
    for measure in rv:
        for sensor_id in rv[measure]:
            rv[measure][sensor_id] = get_historic_sensors_data_by_sensor(
                session, sensor_id, measure, time_window
            )
    return rv


def get_ecosystems_historic_sensors_data(session: Session,
                                         ecosystems_query_obj: list[Ecosystem],
                                         time_window: timeWindow,
                                         level: Union[
                                             str, tuple, list] = "all",
                                         ) -> list[dict]:
    if isinstance(level, str):
        if level == "all":
            level = ("environment", "plants")
        else:
            level = (level,)

    def get_data(ecosystem_id, level, time_window):
        data_skeleton = _get_sensors_data_skeleton(
            session, ecosystem_id, time_window, level
        )
        return _fill_historic_sensors_data_skeleton(
            session, time_window, data_skeleton
        )

    return [
        {
            "uid": ecosystem.id,
            "name": ecosystem.name,
            "time_window": {
                "start": time_window.start,
                "end": time_window.end,
            },
            "level": level,
            "data": get_data(ecosystem.id, level, time_window),
        }
        for ecosystem in ecosystems_query_obj
    ]


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
            for sensor in sensors_data[ecosystem]["data"][
                    measure]:
                data = sensors_data[ecosystem]["data"][
                    measure][sensor]
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


def get_hardware_by_uid(session: Session,
                        hardware_uid: str) -> list[dict]:
    hardware = (session.query(Hardware)
                       .filter(Hardware.id==hardware_uid)
                       .first())
    if hardware:
        return hardware.to_dict()
    else:
        return {}


def get_hardware(session: Session,
                 ecosystems_query_obj: list[Ecosystem],
                 level: Union[str, tuple, list] = "all",
                 hardware_type: Union[str, tuple, list] = "all"
                 ) -> list[dict]:
    if isinstance(level, str):
        if level == "all":
            level = ("environment", "plants")
        else:
            level = (level,)
    if isinstance(hardware_type, str):
        if hardware_type == "all":
            hardware_type = ALL_HARDWARE
        elif hardware_type == "actuators":
            hardware_type = ALL_HARDWARE.remove("sensor")
        else:
            hardware_type = (hardware_type,)

    return [{
        "uid": ecosystem.id,
        "name": ecosystem.name,
        "hardware": [hardware.to_dict() for hardware in (
            session.query(Hardware).join(Ecosystem)
                .filter(Ecosystem.id == ecosystem.id)
                .filter(Hardware.type.in_(hardware_type))
                .filter(Hardware.level.in_(level))
                .order_by(Hardware.type)
                .order_by(Hardware.level)
                .all()
        )]
    } for ecosystem in ecosystems_query_obj]


def get_plants(session: Session,
               ecosystems_query_obj: list[Ecosystem],
               ) -> list[dict[str]]:
    return [{
        "ecosystem_uid": ecosystem.id,
        "ecosystem_name": ecosystem.name,
        "plants": [
            plant.to_dict()
            for plant in ecosystem.plants
        ]
    } for ecosystem in ecosystems_query_obj]
