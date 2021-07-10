from collections import namedtuple
from datetime import datetime
from typing import Union

from cachetools import cached, TTLCache, FIFOCache
from numpy import mean
from sqlalchemy.orm.session import Session

from app.API.utils import time_limits, timeWindow
from dataspace import sensorsData
from app.models import sensorData, Hardware, Ecosystem, Health, Management, engineManager, Service


max_ecosystems = 32

cache_ecosystem_info = TTLCache(maxsize=max_ecosystems, ttl=60)
cache_sensors_data_skeleton = TTLCache(maxsize=max_ecosystems, ttl=900)
cache_sensors_data_raw = TTLCache(maxsize=max_ecosystems*32, ttl=900)
cache_sensors_data_average = TTLCache(maxsize=max_ecosystems, ttl=300)
cache_sensors_data_summary = TTLCache(maxsize=max_ecosystems*2, ttl=300)


ecosystemIds = namedtuple("ecosystemIds", ("uid", "name"))


def on_off(value: bool) -> str:
    if value:
        return "on"
    return "off"


def get_manager_query_obj(*managers: str,
                          session: Session,
                          time_limit: datetime = None,
                          connected: bool = False) -> list:
    if managers:
        base_query = (session.query(engineManager)
                      .filter((engineManager.uid.in_(managers)) |
                              (engineManager.sid.in_(managers)))
                      )
    else:
        base_query = session.query(engineManager)
    mid_query = base_query

    if time_limit:
        mid_query = base_query.filter(engineManager.last_seen >= time_limit)

    end_query = mid_query
    if connected:
        end_query = mid_query.filter(engineManager.connected == True)

    manager_qo = end_query.all()

    return manager_qo


def get_ecosystem_ids(ecosystem: str,
                      session: Session,
                      time_limit: datetime = None) -> ecosystemIds:
    base_query = (session.query(Ecosystem).join(engineManager)
                         .filter((Ecosystem.id == ecosystem) |
                                 (Ecosystem.name == ecosystem))
                  )
    if time_limit == "connected":
        ids = base_query.filter(engineManager.connected).first()
    elif time_limit:
        ids = base_query.filter(Ecosystem.last_seen >= time_limit).first()
    else:
        ids = base_query.first()
    if ids:
        return ecosystemIds(ids.id, ids.name)
    return ()


# TODO: add a s to ecosystem
def get_ecosystem_query_obj(*ecosystems: str,
                            session: Session,
                            time_limit: datetime = None,
                            connected: bool = False) -> list:

    if ecosystems:
        base_query = (session.query(Ecosystem).join(engineManager)
                      .filter((Ecosystem.id.in_(ecosystems)) |
                              (Ecosystem.name.in_(ecosystems)))
                      )
    else:
        base_query = session.query(Ecosystem).join(engineManager)

    mid_query = base_query
    if time_limit:
        mid_query = (
            base_query.filter(Ecosystem.last_seen >= time_limit)
        )

    end_query = mid_query
    if connected:
        end_query = mid_query.filter(engineManager.connected)

    ecosystems_qo = end_query.all()

    return ecosystems_qo


def get_connected_ecosystems_query_obj(session: Session) -> list:
    ecosystems_qo = get_ecosystem_query_obj(
        session=session, connected=True)
    return ecosystems_qo


def get_recent_ecosystems_query_obj(session: Session):
    time_limit = time_limits()["recent"]
    ecosystems_qo = get_ecosystem_query_obj(
        time_limit=time_limit, session=session)
    return ecosystems_qo


# TODO: improve
def get_ecosystems_info(ecosystems_query_obj: list[Ecosystem],
                        session: Session) -> dict:
    limits = time_limits()

    def get_info(ecosystem):
        # Dummy function to allow memoization
        @cached(cache_ecosystem_info)
        def cached_func(ecosystem_id):
            return {
                "name": ecosystem.name,
                "connected": ecosystem.manager.connected,
                "status": ecosystem.status,
                "webcam": ecosystem.manages(Management["webcam"]),
                "lighting": True if (
                        ecosystem.manages(Management["light"])
                        and ecosystem.hardware.filter_by(type="light").first()
                ) else False,
                "health": True if (
                    session.query(Health)
                    .filter_by(ecosystem_id=ecosystem.id)
                    .filter(Health.datetime >= limits["health"])
                    .first()
                    ) else False,
                "env_sensors": True if (
                    session.query(Hardware)
                    .filter_by(ecosystem_id=ecosystem.id)
                    .filter_by(type="sensor", level="environment")
                    .filter(Hardware.last_log >= limits["sensors"])
                    .first()
                    ) else False,
                "plant_sensors": True if (
                    session.query(Hardware)
                    .filter_by(ecosystem_id=ecosystem.id)
                    .filter_by(type="sensor", level="plants")
                    .filter(Hardware.last_log >= limits["sensors"])
                    .first()
                    ) else False,
                "switches": True if ecosystem.hardware.filter_by(type="light").first()
                            and ecosystem.manages(Management["light"])
                            and ecosystem.id in sensorsData else False,
            }
        return cached_func(ecosystem.id)

    ecosystems_info = {ecosystem.id: get_info(ecosystem)
                       for ecosystem in ecosystems_query_obj}
    return ecosystems_info


def summarize_ecosystems_info(ecosystems_info: dict, session: Session) -> dict:
    return {
        "webcam": [{"id": ecosystem, "name": ecosystems_info[ecosystem]["name"]}
                   for ecosystem in ecosystems_info
                   if ecosystems_info[ecosystem]["webcam"]]
                   if "webcam" in [s.name for s in session.query(Service)
                                    .filter_by(status=1)
                                    .all()]
                  else [],
        # TODO: check that we have valid lighting times
        "lighting": [{"id": ecosystem, "name": ecosystems_info[ecosystem]["name"]}
                     for ecosystem in ecosystems_info
                     if ecosystems_info[ecosystem]["lighting"]],
        "health": [{"id": ecosystem, "name": ecosystems_info[ecosystem]["name"]}
                   for ecosystem in ecosystems_info
                   if ecosystems_info[ecosystem]["health"]],
        "env_sensors": [{"id": ecosystem, "name": ecosystems_info[ecosystem]["name"]}
                        for ecosystem in ecosystems_info
                        if ecosystems_info[ecosystem]["env_sensors"]],
        "plant_sensors": [{"id": ecosystem, "name": ecosystems_info[ecosystem]["name"]}
                          for ecosystem in ecosystems_info
                          if ecosystems_info[ecosystem]["plant_sensors"]],
        "switches": [{"id": ecosystem, "name": ecosystems_info[ecosystem]["name"]}
                     for ecosystem in ecosystems_info
                     if ecosystems_info[ecosystem]["switches"]],
    }


def get_light_info(ecosystems_query_obj: list[Ecosystem]) -> dict:
    def try_iso_format(timeobj):
        try:
            return timeobj.isoformat()
        except AttributeError:
            return None

    info = {}

    for ecosystem in ecosystems_query_obj:
        light = ecosystem.light.first()
        info[ecosystem.id] = {
            "name": ecosystem.name,
            "active": ecosystem.manages(Management["light"]),
            "status": light.status,
            "mode": light.mode,
            "method": light.method,
            "lighting_hours": {
                "morning_start": try_iso_format(light.morning_start),
                "morning_end": try_iso_format(light.morning_end),
                "evening_start": try_iso_format(light.evening_start),
                "evening_end": try_iso_format(light.evening_end),
            },
        }
    return info


def get_raw_current_sensors_data() -> dict:
    """ Get the current data for the given ecosystems

    Returns a dict with the current data for the given ecosystems if they exist
    and recently sent sensors data.
    """
    return {**sensorsData}


def get_current_sensors_data(*ecosystems: str, session: Session) -> dict:
    """ Get the current data for the given ecosystems

    Returns a dict with the current data for the given ecosystems if they exist
    and recently sent sensors data.
    """
    if not ecosystems:
        ecosystems = [uid for uid in sensorsData]
    data = {}
    for ecosystem in ecosystems:
        ids = get_ecosystem_ids(ecosystem, session)
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


def get_sensors_data_skeleton(session: Session,
                              ecosystem_id: str,
                              time_window: timeWindow,
                              level: tuple[str] = ("environment", "plants"),
                              ) -> dict:
    rv = {}

    # No group_by: Faster by 0.2 ms in small dataset
    subquery = (
        session.query(sensorData.sensor_id).join(Hardware)
            .filter(Hardware.level.in_(level))
            .filter(sensorData.ecosystem_id == ecosystem_id)
            .filter((sensorData.datetime > time_window[0]) &
                    (sensorData.datetime <= time_window[1]))
            .subquery()
    )

    sensors = (
        session.query(Hardware).filter(Hardware.id.in_(subquery)).all()
    )

    for sensor in sensors:
        for measure in sensor.measure:
            try:
                rv[measure.name][sensor.id] = {}
            except KeyError:
                rv[measure.name] = {sensor.id: {}}
    return rv


@cached(cache_sensors_data_raw)
def get_historic_sensor_data(session: Session,
                             ecosystem_id: str,
                             sensor_id: str,
                             measure: str,
                             time_window: timeWindow) -> dict:
    sensor_name = session.query(Hardware).filter(
        Hardware.id == sensor_id).one().name
    values = (session.query(sensorData)
              .filter(sensorData.ecosystem_id == ecosystem_id)
              .filter(sensorData.measure == measure)
              .filter(sensorData.sensor_id == sensor_id)
              .filter((sensorData.datetime > time_window[0]) &
                      (sensorData.datetime <= time_window[1]))
              .with_entities(sensorData.datetime,
                             sensorData.value)
              .all()
              )
    return {
        "name": sensor_name,
        "values": values,
    }


def get_ecosystems_historic_sensors_data(ecosystems_query_obj: list[Ecosystem],
                                         session: Session,
                                         time_window: timeWindow,
                                         level: tuple = ("environment", "plants"),
                                         ) -> dict:
    def get_data(ecosystem_id, level, time_window):
        rv = get_sensors_data_skeleton(
            session, ecosystem_id, time_window, level
        )
        for measure in rv:
            for sensor_id in rv[measure]:
                rv[measure][sensor_id] = get_historic_sensor_data(
                    session, ecosystem_id, sensor_id, measure, time_window
                )
        return rv

    return {
        ecosystem.id: {
            "name": ecosystem.name,
            "time_window": {
                "start": time_window.start,
                "end": time_window.end,
            },
            "data": get_data(ecosystem.id, level, time_window),
        }
        for ecosystem in ecosystems_query_obj
    }


def average_historic_sensors_data(sensors_data: dict,
                                  precision: int = 2) -> dict:
    # Dummy function to allow memoization
    @cached(cache_sensors_data_average)
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

    return {ecosystem: average_data(ecosystem, sensors_data[ecosystem]["time_window"])
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


def get_hardware(ecosystems_query_obj: list[Ecosystem],
                 session: Session,
                 level: Union[str, tuple, list] = "all",
                 hardware_type: Union[str, tuple, list] = "all"
                 ) -> dict:
    all_hardware = ["sensor", "light", "heater", "cooler", "humidifier",
                    "dehumidifier"]
    if isinstance(level, str):
        if level == "all":
            level = ("environment", "plants")
        else:
            level = (level, )
    if isinstance(hardware_type, str):
        if hardware_type == "all":
            hardware_type = all_hardware
        elif hardware_type == "actuators":
            hardware_type = all_hardware.remove("sensor")
        else:
            hardware_type = (hardware_type, )

    result = {}

    for ecosystem in ecosystems_query_obj:
        result[ecosystem.id] = {}

        for hardware in (
                session.query(Hardware).join(Ecosystem)
                       .filter(Ecosystem.id == ecosystem.id)
                       .filter(Hardware.type.in_(hardware_type))
                       .filter(Hardware.level.in_(level))
                       .order_by(Hardware.type)
                       .order_by(Hardware.level)
                       .all()
        ):
            result[ecosystem.id][hardware.id] = {
                "name": hardware.name,
                "address": hardware.address,
                "level": hardware.level,
                "type": hardware.type,
                "model": hardware.model,
                "last_log": hardware.last_log,
            }

    return result
