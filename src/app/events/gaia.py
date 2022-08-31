import asyncio
from asyncio import sleep
from datetime import datetime, time, timezone
import logging
import random
import typing as t

import cachetools
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from statistics import mean, stdev as std

from .decorators import registration_required
from src import api
from src.app import app_config, db, dispatcher, sio
from src.app.utils import decrypt_uid, validate_uid_token
from src.database.models.gaia import (
    Ecosystem, Engine, EnvironmentParameter, Hardware, Health, Light,
    Management, Measure, SensorHistory
)


sio_logger = logging.getLogger(f"{app_config['APP_NAME'].lower()}.socketio")
# TODO: better use
collector_logger = logging.getLogger(f"{app_config['APP_NAME'].lower()}.collector")


_BACKGROUND_TASK_STARTED = False
# TODO: create a thread local asyncio name for loop

summarize = {"mean": mean, "std": std}


# TODO: share for gaia and clients
engines_blacklist = cachetools.TTLCache(maxsize=62, ttl=60 * 60 * 24)


def try_time_from_iso(iso_str: str) -> t.Optional[time]:
    try:
        return time.fromisoformat(iso_str)
    except (TypeError, AttributeError):
        return None


def clear_client_blacklist(client_address: str = None) -> None:
    global engines_blacklist
    if not client_address:
        engines_blacklist = cachetools.TTLCache(maxsize=62, ttl=60 * 60 * 24)
    else:
        try:
            del engines_blacklist[client_address]
        except KeyError:
            pass


async def update_engine_or_create_it(
        session: AsyncSession,
        engine_info: t.Optional[dict] = None,
        uid: t.Optional[str] = None,
) -> Engine:
    engine_info = engine_info or {}
    uid = uid or engine_info.pop("uid", None)
    if not uid:
        raise ValueError(
            "Provide uid either as an argument or as a key in the updated info"
        )
    engine = await api.gaia.get_engine(session, uid)
    if not engine:
        engine_info["uid"] = uid
        engine = await api.gaia.create_engine(session, engine_info)
    elif engine_info:
        await api.gaia.update_engine(session, engine_info, uid)
    return engine


async def update_ecosystem_or_create_it(
        session: AsyncSession,
        ecosystem_info: t.Optional[dict] = None,
        uid: t.Optional[str] = None,
) -> Ecosystem:
    ecosystem_info = ecosystem_info or {}
    uid = uid or ecosystem_info.pop("uid", None)
    if not uid:
        raise ValueError(
            "Provide uid either as an argument or as a key in the updated info"
        )
    ecosystem = await api.gaia.get_ecosystem(session, uid)
    if not ecosystem:
        ecosystem_info["uid"] = uid
        ecosystem = await api.gaia.create_ecosystem(session, ecosystem_info)
    elif ecosystem_info:
        await api.gaia.update_ecosystem(session, ecosystem_info, uid)
    return ecosystem


async def update_hardware_or_create_it(
        session: AsyncSession,
        hardware_info: t.Optional[dict] = None,
        uid: t.Optional[str] = None,
) -> Hardware:
    hardware_info = hardware_info or {}
    uid = uid or hardware_info.pop("uid", None)
    if not uid:
        raise ValueError(
            "Provide uid either as an argument or as a key in the updated info"
        )
    hardware = await api.gaia.get_hardware(session, uid)
    if not hardware:
        hardware_info["uid"] = uid
        # TODO: solve
        hardware_info.pop("measure", None)
        hardware = await api.gaia.create_hardware(session, hardware_info)
    elif hardware_info:
        await api.gaia.update_ecosystem(session, hardware_info, uid)
    return hardware


async def update_environment_parameter_or_create_it(
        session: AsyncSession,
        uid: t.Optional[str] = None,
        parameter: t.Optional[str] = None,
        parameter_info: t.Optional[dict] = None,
) -> EnvironmentParameter:
    parameter_info = parameter_info or {}
    uid = uid or parameter_info.pop("uid", None)
    parameter = parameter or parameter_info.pop("parameter", None)
    if not (uid or parameter):
        raise ValueError(
            "Provide uid and parameter either as a argument or as a key in the "
            "updated info"
        )
    environment_parameter = await api.gaia.get_environmental_parameter(
        session, uid=uid, parameter=parameter
    )
    if not environment_parameter:
        parameter_info["ecosystem_uid"] = uid
        parameter_info["parameter"] = parameter
        environment_parameter = await api.gaia.create_environmental_parameter(
            session, parameter_info
        )
    elif parameter_info:
        await api.gaia.update_environmental_parameter(
            session, parameter_info, uid
        )
    return environment_parameter


# TODO: use a Namespace that uses parameter dispatcher and db_session
# ---------------------------------------------------------------------------
#   Data requests to engineManagers
# ---------------------------------------------------------------------------
async def request_sensors_data(room="engineManagers"):
    sio_logger.debug(f"Sending sensors data request to {room}")
    await sio.emit("send_sensors_data", namespace="/gaia", room=room)


async def request_config(room="engineManagers"):
    sio_logger.debug(f"Sending config request to {room}")
    await sio.emit("send_config", namespace="/gaia", room=room)


async def request_health_data(room="engineManagers"):
    sio_logger.debug(f"Sending health data request to {room}")
    await sio.emit("send_health_data", namespace="/gaia", room=room)


async def request_light_data(room="engineManagers"):
    sio_logger.debug(f"Sending light data request to {room}")
    await sio.emit("send_light_data", namespace="/gaia", room=room)


async def gaia_background_task():
    while True:
        await sio.emit("ping", namespace="/gaia", room="engineManagers")
        await sleep(15)


# ---------------------------------------------------------------------------
#   SocketIO events coming from Gaia instances
# ---------------------------------------------------------------------------
@sio.on("connect", namespace="/gaia")
async def connect_on_gaia(sid, environ):
    global _BACKGROUND_TASK_STARTED
    if not _BACKGROUND_TASK_STARTED:
        loop = asyncio.get_event_loop()
        loop.create_task(gaia_background_task())
        _BACKGROUND_TASK_STARTED = True
    async with sio.session(sid, namespace="/gaia") as session:
        remote_addr = session["REMOTE_ADDR"] = environ["REMOTE_ADDR"]
        attempts = engines_blacklist.get(remote_addr, 0)
        max_attempts: int = app_config.get("GAIA_CLIENT_MAX_ATTEMPT", 2)
        if attempts == max_attempts:
            sio_logger.warning(
                f"Received {max_attempts} invalid registration requests "
                f"from {remote_addr}."
            )
        if attempts >= max_attempts:
            over_attempts = attempts - max_attempts
            if over_attempts > 4:
                over_attempts = 4
            fix_tempering = 1.5 ** over_attempts  # max 5 secs
            random_tempering = 2 * random.random() - 1  # [-1: 1]
            await sio.sleep(fix_tempering + random_tempering)
            engines_blacklist[remote_addr] += 1
            return False


@sio.on("disconnect", namespace="/gaia")
async def disconnect(sid):
    async with db.scoped_session() as session:
        engine = await api.gaia.get_engine(session, engine_id=sid)
        if not engine:
            return
        uid = engine.uid
        sio.leave_room(sid, "engineManagers", namespace="/gaia")
        engine.connected = False
        session.commit()
        await sio.emit(
            "ecosystem_status",
            {ecosystem.uid: {"status": ecosystem.status, "connected": False}
             for ecosystem in engine.ecosystems},
            namespace="/"
        )
        sio_logger.info(f"Manager {uid} disconnected")


@sio.on("pong", namespace="/gaia")
async def pong(sid, data):
    now = datetime.now(timezone.utc).replace(microsecond=0)
    async with db.scoped_session() as session:
        engine = await api.gaia.get_engine(session, sid)
        if not engine:
            return
        engine.last_seen = now
        for ecosystem_uid in data:
            ecosystem = await api.gaia.get_ecosystem(ecosystem_uid)
            ecosystem.last_seen = now
        await session.commit()


@sio.on("register_engine", namespace="/gaia")
async def register_manager(sid, data):
    async with sio.session(sid, namespace="/gaia") as session:
        remote_addr = session["REMOTE_ADDR"]
        engine_uid = decrypt_uid(data["ikys"])
        if validate_uid_token(data["uid_token"], engine_uid):
            session["engine_uid"] = engine_uid
    if not validate_uid_token(data["uid_token"], engine_uid):
        try:
            engines_blacklist[remote_addr] += 1
        except KeyError:
            engines_blacklist[remote_addr] = 0
        sio_logger.info(
            f"Received invalid registration request from {remote_addr}")
        await sio.disconnect(sid, namespace="/gaia")
    else:
        try:
            del engines_blacklist[remote_addr]
        except KeyError:
            pass
        now = datetime.now(timezone.utc).replace(microsecond=0)
        engine_info = {
            "uid": engine_uid,
            "sid": sid,
            "connected": True,
            "registration_date": now,
            "last_seen": now,
            "address": f"{remote_addr}",
        }
        async with db.scoped_session() as session:
            await update_engine_or_create_it(session, engine_info)
        sio.enter_room(sid, room="engine", namespace="/gaia")

        await sio.emit("register_ack", namespace="/gaia", room=sid)
        sio_logger.info(f"Successful registration of engine {engine_uid}, "
                        f"from {remote_addr}")
        await request_config(sid)
        await request_sensors_data(sid)
        await request_light_data(sid)
        await request_health_data(sid)


@sio.on("engines_change", namespace="/gaia")
@registration_required
def reload_all(sid, data):
    request_config(sid)
    request_sensors_data(sid)
    request_light_data(sid)
    request_health_data(sid)


@sio.on("base_info", namespace="/gaia")
@registration_required
async def update_base_info(sid, data, engine_uid):
    ecosystems = []
    for ecosystem_data in data:
        ecosystem_data.update({"engine_uid": engine_uid})
        uid: str = ecosystem_data["uid"]
        async with db.scoped_session() as session:
            await update_ecosystem_or_create_it(session, ecosystem_data)
        ecosystems.append({"uid": uid, "status": ecosystem_data["status"]})
    await sio.emit(
        "ecosystem_status",
        [{
            "uid": ecosystem["uid"],
            "status": ecosystem["status"],
            "connected": True
        } for ecosystem in ecosystems],
        namespace="/"
    )


@sio.on("management", namespace="/gaia")
@registration_required
async def update_management(sid, data, engine_uid):
    async with db.scoped_session() as session:
        for ecosystem_data in data:
            uid: str = ecosystem_data["uid"]
            ecosystem = await update_ecosystem_or_create_it(session, uid=uid)
            for m, v in Management.items():
                try:
                    if ecosystem_data[m]:
                        ecosystem.add_management(v)
                except KeyError:
                    # Not implemented in gaia yet
                    pass
            session.add(ecosystem)
        await session.commit()


@sio.on("environmental_parameters", namespace="/gaia")
@registration_required
async def update_environmental_parameters(sid, data, engine_uid):
    async with db.scoped_session() as session:
        for ecosystem_data in data:
            uid: str = ecosystem_data["uid"]
            tods = {}
            env_params = {}
            for tod in ["day", "night"]:
                params = ecosystem_data.get(tod)
                if params:
                    time_str = params.get("start")
                    if time_str:
                        tods[tod] = datetime.strptime(time_str, "%Hh%M").time()
                    else:
                        tods[tod] = None
                    climate_params = params.get("climate", {})
                    for param in climate_params:
                        try:
                            env_params[param].update({tod: climate_params[param]})
                        except KeyError:
                            env_params.update({param: {tod: climate_params[param]}})
            for param in env_params:
                env_params[param].update(
                    {"hysteresis": ecosystem_data.get("hysteresis", {}).get(param)}
                )
            ecosystem_info = {
                "uid": uid,
                "day_start": tods.get("day"),
                "night_start": tods.get("night"),
            }
            ecosystem = await update_ecosystem_or_create_it(
                session, ecosystem_info=ecosystem_info
            )
            ecosystem.light.method = ecosystem_data.get("light")
            for (parameter, v) in env_params.items():
                parameter_info = {
                    "day": v.get("day"),
                    "night": v.get("night"),
                    "hysteresis": v.get("hysteresis")
                }
                await update_environment_parameter_or_create_it(
                    session, uid, parameter, parameter_info
                )
        await session.commit()


@sio.on("hardware", namespace="/gaia")
@registration_required
async def update_hardware(sid, data, engine_uid):
    async with db.scoped_session() as session:
        for ecosystem_data in data:
            uid = ecosystem_data.pop("uid")
            for hardware_uid, hardware_dict in ecosystem_data.items():
                hardware_dict["ecosystem_uid"] = uid
                # TODO: solve
                address = hardware_dict.pop("address")
                type_ = hardware_dict.pop("type")
                hardware = await update_hardware_or_create_it(
                    session, hardware_info=hardware_dict, uid=hardware_uid
                )
                hardware.address = address
                hardware.type = type_
                measures = hardware_dict.pop("measure", [])
                if isinstance(measures, str):
                    measures = [measures]
                for measure in measures:
                    _measure = await api.gaia.get_measure(session, measure)
                    hardware.measure.append(_measure)
                # TODO: if plants
                for param, value in hardware_dict.items():
                    setattr(hardware, param, value)
                session.merge(hardware)
        session.commit()


# TODO: split this in two part: one receiving and logging data, and move the
#  one sending data to a scheduled event
@sio.on("sensors_data", namespace="/gaia")
@registration_required
async def update_sensors_data(sid, data, engine_uid):
    sio_logger.debug(f"Received 'sensors_data' from engine: {engine_uid}")
    api.gaia.update_current_sensors_data(
        {
            ecosystem["ecosystem_uid"]: {
                "data": {
                    sensor["sensor_uid"]: {
                        measure["name"]: measure["value"]
                        for measure in sensor["measures"]
                    } for sensor in ecosystem["data"]
                },
                "datetime": ecosystem["datetime"]
            } for ecosystem in data
        }
    )
    await sio.emit("current_sensors_data", data, namespace="/")
    async with db.scoped_session() as session:
        for ecosystem in data:
            try:
                dt = datetime.fromisoformat(ecosystem["datetime"])
            # When launching, gaiaEngine is sometimes still loading its sensors
            #  and doesn't send complete data dict
            except KeyError:
                continue

            if dt.minute % app_config["SENSORS_LOGGING_PERIOD"] == 0:
                measure_values = {}
                collector_logger.debug(f"Logging sensors data from ecosystem: {ecosystem['ecosystem_uid']}")

                for sensor in ecosystem["data"]:
                    sensor_uid = sensor["sensor_uid"]
                    for measure in sensor["measures"]:
                        value = float(measure["value"])
                        sensor_data = {
                            "ecosystem_uid": ecosystem["ecosystem_uid"],
                            "sensor_uid": sensor_uid,
                            "measure": measure["name"],
                            "datetime": dt,
                            "value": value,
                        }
                        try:
                            await api.gaia.create_historic_sensor_data(
                                session, sensor_data
                            )
                            await api.gaia.update_hardware(
                                session, {"last_log": dt}, sensor_uid
                            )
                        except IntegrityError:
                            collector_logger.warning(
                                f"Already have a {measure['name']} data point at {dt} "
                                f"for {sensor_uid}"
                            )

                        try:
                            measure_values[measure["name"]].append(value)
                        except KeyError:
                            measure_values[measure["name"]] = [value]

                for method in summarize:
                    for measure in measure_values:
                        # Set a minimum threshold before summarizing values
                        # TODO: add the option to summarize or not
                        if len(measure_values[measure]) >= 3:
                            values_summarized = round(
                                summarize[method](measure_values[measure]), 2
                            )
                            aggregated_data = {
                                "ecosystem_uid": ecosystem["ecosystem_uid"],
                                "sensor_uid": method,
                                "measure": measure,
                                "datetime": dt,
                                "value": values_summarized,
                            }
                            await api.gaia.create_historic_sensor_data(
                                session, aggregated_data
                            )
        await session.commit()


"""
@sio.on("health_data", namespace="/gaia")
def update_health_data(data):
    manager = get_engine("config")
    if manager:
        sio_logger.debug(f"Received 'update_health_data' from {manager.uid}")
        dispatcher.emit("application", "health_data", data=data)
        # healthData.update(data)
        for d in data:
            health = Health(
                ecosystem_uid=d["ecosystem_uid"],
                datetime=datetime.fromisoformat(d["datetime"]),
                green=d["green"],
                necrosis=d["necrosis"],
                health_index=d["health_index"]
            )
            db.session.add(health)
        db.session.commit()


@sio.on("light_data", namespace="/gaia")
def update_light_data(data):
    # TODO: log status 
    manager = get_engine("config")

    if manager:
        sio_logger.debug(f"Received 'light_data' from {manager.uid}")
        for d in data:
            morning_start = try_time_from_iso(d.get("morning_start", None))
            morning_end = try_time_from_iso(d.get("morning_end", None))
            evening_start = try_time_from_iso(d.get("evening_start", None))
            evening_end = try_time_from_iso(d.get("evening_end", None))
            light = Light(
                ecosystem_uid=d["ecosystem_uid"],
                status=d["status"],
                mode=d["mode"],
                method=d["method"],
                morning_start=morning_start,
                morning_end=morning_end,
                evening_start=evening_start,
                evening_end=evening_end
            )
            db.session.merge(light)
        db.session.commit()
        sio.emit("light_data", data, namespace="/")
"""


# ---------------------------------------------------------------------------
#   Dispatcher events
# ---------------------------------------------------------------------------
@dispatcher.on("turn_light")
def _turn_light(*args, **kwargs):
    # TODO: create async dispatcher or wrap in async_to_sync
    sio.emit("turn_light", namespace="/gaia", **kwargs)


@dispatcher.on("turn_actuator")
def _turn_actuator(*args, **kwargs):
    # TODO: create async dispatcher or wrap in async_to_sync
    sio.emit("turn_actuator", namespace="/gaia", **kwargs)
