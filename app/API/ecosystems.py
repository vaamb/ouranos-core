from collections import namedtuple
from datetime import datetime

import cachetools.func
from cachetools import cached, TTLCache
from numpy import mean

from app.API.utils import time_limits, get_weather_data
from app.dataspace import sensorsData, sensorsDataHistory
from app.models import sensorData, Hardware, Ecosystem, Health, Management, engineManager, Service


max_ecosystems = 32

cache_ecosystem_info = TTLCache(maxsize=max_ecosystems, ttl=60)
cache_sensors_data_raw = TTLCache(maxsize=max_ecosystems, ttl=900)
cache_sensors_data_average = TTLCache(maxsize=max_ecosystems, ttl=300)
cache_sensors_data_summary = TTLCache(maxsize=max_ecosystems*2, ttl=300)


ids_tuple = namedtuple("ecosystem_ids", ["uid", "name"])


def on_off(value: bool) -> str:
    if value:
        return "on"
    return "off"


def get_manager_query_obj(*managers,
                          session,
                          time_limit: datetime = None,
                          connected: bool = False) -> list:
    pass


@cachetools.func.ttl_cache(maxsize=max_ecosystems, ttl=5)
def get_ecosystem_ids(ecosystem: str, session, time_limit) -> tuple:
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
        return ids_tuple(ids.id, ids.name)
    return ()


# @cachetools.func.ttl_cache(maxsize=max_ecosystems, ttl=5*60)
def get_ecosystem_query_obj(*ecosystems,
                            session,
                            time_limit: datetime = None,
                            connected: bool = False) -> list:

    if ecosystems:
        base_query = (session.query(Ecosystem).join(engineManager)
                      .filter((Ecosystem.id.in_(ecosystems)) |
                              (Ecosystem.name.in_(ecosystems)))
                     )
    else:
        base_query = session.query(Ecosystem)

    mid_query = base_query
    if time_limit:
        mid_query = (base_query
                     .filter(Ecosystem.last_seen >= time_limit)
                     )

    end_query = mid_query
    if connected:
        end_query = mid_query.filter(engineManager.connected)

    ecosystems_qo = end_query.all()

    return ecosystems_qo


def get_connected_ecosystems_query_obj(session) -> list:
    ecosystems_qo = get_ecosystem_query_obj(session=session,
                                            connected=True)
    return ecosystems_qo


def get_recent_ecosystems_query_obj(session):
    time_limit = time_limits()["recent"]
    ecosystems_qo = get_ecosystem_query_obj(time_limit=time_limit, session=session)
    return ecosystems_qo


def get_ecosystems_info(ecosystems_query_obj, session) -> dict:
    limits = time_limits()

    # Dummy function to allow memoization
    @cached(cache_ecosystem_info)
    def get_info(ecosystem):
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

    ecosystems_info = {ecosystem.id: get_info(ecosystem) for ecosystem in ecosystems_query_obj}
    return ecosystems_info


def summarize_ecosystems_info(ecosystems_info, session):
    return {
        "webcam": [{"id": ecosystem, "name": ecosystems_info[ecosystem]["name"]}
                   for ecosystem in ecosystems_info
                   if ecosystems_info[ecosystem]["webcam"]]
                  if "webcam" in [s.name for s in session.query(Service)
                                   .filter_by(status=1)
                                   .all()]
                  else [],
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


def get_app_functionalities(summarized_ecosystems_info):
    app_functionalities = summarized_ecosystems_info
    app_functionalities["weather"] = True if get_weather_data() else False
    return app_functionalities


def get_light_info(ecosystems_query_obj) -> dict:
    info = {}
    for ecosystem in ecosystems_query_obj:
        light = ecosystem.light.first()
        info[ecosystem.id] = {
            "name": ecosystem.name,
            "status": light.status,
            "mode": light.mode,
        }
    return info


# TODO: add a level filter?
def get_current_sensors_data(*ecosystems, session) -> dict:
    """ Get the current data for the given ecosystems

    Returns a dict with the current data for the given ecosystems if they exist
    and recently sent sensors data.
    """
    if not ecosystems:
        ecosystems = [id for id in sensorsData]
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


# TODO: make sure it is done outside the main process when querying more
#  than one ecosystem as it is quite expensive
def get_historic_sensors_data(ecosystems_query_obj,
                              session,
                              level: tuple = (),
                              time_windows: tuple = (None, None),
                              ) -> dict:

    if not level:
        level = ("environment", "plants")

    if not time_windows[0]:
        window_start = time_limits()["sensors"]
    else:
        window_start = time_windows[0]

    if not time_windows[1]:
        window_end = datetime.now().replace(tzinfo=None)
    else:
        window_end = time_windows[1]

    # Dummy function to allow memoization
    @cached(cache_sensors_data_raw)
    def get_data(ecosystem):
        data = {}
        if level:
            base_filter = (session.query(sensorData).join(Hardware)
                           .filter(Hardware.level.in_(level))
                           )
        else:
            base_filter = session.query(sensorData).join(Hardware)

        measures = [
            d.measure for d in
            base_filter
                .filter(sensorData.ecosystem_id == ecosystem.id)
                .filter((sensorData.datetime > window_start) &
                        (sensorData.datetime <= window_end))
                .group_by(sensorData.measure)
                .all()
        ]

        for measure in measures:
            data[measure] = {}
            data_points = (session.query(sensorData).join(Hardware)
                           .filter(sensorData.ecosystem_id == ecosystem.id)
                           .filter(Hardware.level.in_(level))
                           .filter(sensorData.measure == measure)
                           .group_by(sensorData.sensor_id)
                           .all()
                           )

            for data_point in data_points:
                values = (session.query(sensorData).join(Hardware)
                          .filter(sensorData.ecosystem_id == ecosystem.id)
                          .filter(Hardware.level.in_(level))
                          .filter(sensorData.measure == measure)
                          .filter(sensorData.sensor_id == data_point.sensor.id)
                          .filter((sensorData.datetime > window_start) &
                                  (sensorData.datetime <= window_end))
                          .with_entities(sensorData.datetime,
                                         sensorData.value)
                          .all()
                          )
                data[measure][data_point.sensor.id] = {
                    "name": data_point.sensor.name,
                    "values": values
                }
        return data

    return {
        ecosystem.id: {
            "name": ecosystem.name,
            "time_window": {
                "start": window_start,
                "end": window_end,
            },
            "data": get_data(ecosystem),
        }
        for ecosystem in ecosystems_query_obj
    }


def average_historic_sensors_data(sensors_data: dict, precision: int = 2):
    # Dummy function to allow memoization
    @cached(cache_sensors_data_average)
    def average_data(ecosystem):
        summary = {
            "name": sensors_data[ecosystem]["name"],
            "time_window": sensors_data[ecosystem]["time_window"],
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

    return {ecosystem: average_data(ecosystem)
            for ecosystem in sensors_data}


def summarize_sensors_data(sensors_data: dict, precision: int = 2):
    # Dummy function to allow memoization
    @cached(cache_sensors_data_summary)
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
