import asyncio
from asyncio import sleep
from datetime import datetime, time, timezone
import logging
import random
import typing as t

import cachetools
from socketio import AsyncNamespace
from sqlalchemy.exc import IntegrityError
from statistics import mean, stdev as std

from .decorators import registration_required
from src.core import api, dispatcher
from src.core.g import app_config, db
from src.core.utils import decrypt_uid, validate_uid_token


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


class Events:
    async def emit(self):
        raise NotImplementedError

    async def gaia_background_task(self):
        while True:
            await self.emit("ping", namespace="/gaia", room="engines")
            await sleep(15)

    # ---------------------------------------------------------------------------
    #   Data requests to Engines
    # ---------------------------------------------------------------------------
    async def request_sensors_data(self, room="engines"):
        sio_logger.debug(f"Sending sensors data request to {room}")
        await self.emit("send_sensors_data", namespace="/gaia", room=room)

    async def request_config(self, room="engines"):
        sio_logger.debug(f"Sending config request to {room}")
        await self.emit("send_config", namespace="/gaia", room=room)

    async def request_health_data(self, room="engines"):
        sio_logger.debug(f"Sending health data request to {room}")
        await self.emit("send_health_data", namespace="/gaia", room=room)

    async def request_light_data(self, room="engines"):
        sio_logger.debug(f"Sending light data request to {room}")
        await self.emit("send_light_data", namespace="/gaia", room=room)

    # ---------------------------------------------------------------------------
    #   SocketIO socketio coming from Gaia instances
    # ---------------------------------------------------------------------------
    async def on_connect(self, sid, environ):
        global _BACKGROUND_TASK_STARTED
        if not _BACKGROUND_TASK_STARTED:
            loop = asyncio.get_event_loop()
            loop.create_task(self.gaia_background_task())
            _BACKGROUND_TASK_STARTED = True
        async with self.session(sid, namespace="/gaia") as session:
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
                await sleep(fix_tempering + random_tempering)
                engines_blacklist[remote_addr] += 1
                return False

    async def on_disconnect(self, sid):
        async with db.scoped_session() as session:
            engine = await api.engine.get(session, engine_id=sid)
            if not engine:
                return
            uid = engine.uid
            self.leave_room(sid, "engines", namespace="/gaia")
            engine.connected = False
            await self.emit(
                "ecosystem_status",
                {ecosystem.uid: {"status": ecosystem.status, "connected": False}
                 for ecosystem in engine.ecosystems},
                namespace="/"
            )
            sio_logger.info(f"Engine {uid} disconnected")

    async def on_pong(self, sid, data):
        now = datetime.now(timezone.utc).replace(microsecond=0)
        async with db.scoped_session() as session:
            engine = await api.engine.get(session, sid)
            if not engine:
                return
            engine.last_seen = now
            for ecosystem_uid in data:
                ecosystem = await api.ecosystem.get(session, ecosystem_uid)
                ecosystem.last_seen = now

    async def on_register_engine(self, sid, data):
        async with self.session(sid) as session:
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
            await self.disconnect(sid)
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
                await api.engine.update_or_create(session, engine_info)
            self.enter_room(sid, room="engines", namespace="/gaia")

            await self.emit("register_ack", namespace="/gaia", room=sid)
            sio_logger.info(f"Successful registration of engine {engine_uid}, "
                            f"from {remote_addr}")
            await self.engines_change(sid)

    async def engines_change(self, sid):
        await self.request_config(sid)
        await self.request_sensors_data(sid)
        await self.request_light_data(sid)
        await self.request_health_data(sid)

    @registration_required
    async def on_engines_change(self, sid, data, engine_uid):
        await self.engines_change(sid)

    @registration_required
    async def on_base_info(self, sid, data, engine_uid):
        ecosystems = []
        for ecosystem_data in data:
            ecosystem_data.update({"engine_uid": engine_uid})
            uid: str = ecosystem_data["uid"]
            async with db.scoped_session() as session:
                await api.ecosystem.update_or_create(session, ecosystem_data)
            ecosystems.append({"uid": uid, "status": ecosystem_data["status"]})
        await self.emit(
            "ecosystem_status",
            [{
                "uid": ecosystem["uid"],
                "status": ecosystem["status"],
                "connected": True
            } for ecosystem in ecosystems],
            namespace="/"
        )

    @registration_required
    async def on_update_management(self, sid, data, engine_uid):
        async with db.scoped_session() as session:
            for ecosystem_data in data:
                uid: str = ecosystem_data["uid"]
                ecosystem = await api.ecosystem.update_or_create(session, uid=uid)
                for m, v in api.Management.items():
                    try:
                        if ecosystem_data[m]:
                            ecosystem.add_management(v)
                    except KeyError:
                        # Not implemented in gaia yet
                        pass
                session.add(ecosystem)

    @registration_required
    async def on_environmental_parameters(self, sid, data, engine_uid):
        async with db.scoped_session() as session:
            for ecosystem_data in data:
                uid: str = ecosystem_data["uid"]
                ecosystem_data["engine_uid"] = engine_uid
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
                ecosystem = await api.ecosystem.update_or_create(
                    session, ecosystem_info=ecosystem_info
                )
                await api.light.update_or_create(
                    session, light_info={"method": ecosystem_data.get("light")},
                    ecosystem_uid=ecosystem.uid
                )
                for (parameter, v) in env_params.items():
                    parameter_info = {
                        "day": v.get("day"),
                        "night": v.get("night"),
                        "hysteresis": v.get("hysteresis")
                    }
                    await api.environmental_parameter.update_or_create(
                        session, uid, parameter, parameter_info
                    )

    @registration_required
    async def on_hardware(self, sid, data, engine_uid):
        async with db.scoped_session() as session:
            for ecosystem_data in data:
                uid = ecosystem_data.pop("uid")
                for hardware_uid, hardware_dict in ecosystem_data.items():
                    hardware_dict["ecosystem_uid"] = uid
                    measures = hardware_dict.pop("measure", [])
                    plants = hardware_dict.pop("plants", [])
                    hardware = await api.hardware.update_or_create(
                        session, hardware_info=hardware_dict, uid=hardware_uid
                    )
                    if measures:
                        if isinstance(measures, str):
                            measures = [measures]
                        measures = [m.replace("_", " ") for m in measures]
                        _measures = await api.measure.get_multiple(session, measures)
                        if _measures:
                            for m in _measures:
                                if m not in hardware.measure:
                                    hardware.measure.append(m)
                    if plants:
                        if isinstance(plants, str):
                            plants = [plants]
                        _plants = await api.plant.get_multiple(session, plants)
                        if _plants:
                            for p in _plants:
                                if p not in hardware.plants:
                                    hardware.plants.append(m)


    # TODO: split this in two part: one receiving and logging data, and move the
    #  one sending data to a scheduled event
    @registration_required
    async def on_sensors_data(self, sid, data, engine_uid):
        sio_logger.debug(f"Received 'sensors_data' from engine: {engine_uid}")
        api.sensor.update_current_data(
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
        await self.emit("current_sensors_data", data, namespace="/")
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
                                await api.sensor.create_record(
                                    session, sensor_data
                                )
                                await api.hardware.update(
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
                                await api.sensor.create_record(
                                    session, aggregated_data
                                )

    @registration_required
    async def on_health_data(self, sid, data, engine_uid):
        sio_logger.debug(f"Received 'update_health_data' from {engine_uid}")
        dispatcher.emit("application", "health_data", data=data)
        # healthData.update(data)
        async with db.scoped_session() as session:
            for d in data:
                health_data = {
                    "ecosystem_uid": d["ecosystem_uid"],
                    "datetime": datetime.fromisoformat(d["datetime"]),
                    "green": d["green"],
                    "necrosis": d["necrosis"],
                    "health_index": d["health_index"]
                }
                await api.health.create_record(session, health_data)

    @registration_required
    async def on_light_data(self, sid, data, engine_uid):
        sio_logger.debug(f"Received 'light_data' from {engine_uid}")
        async with db.scoped_session() as session:
            for d in data:
                morning_start = try_time_from_iso(d.get("morning_start", None))
                morning_end = try_time_from_iso(d.get("morning_end", None))
                evening_start = try_time_from_iso(d.get("evening_start", None))
                evening_end = try_time_from_iso(d.get("evening_end", None))
                light_info = {
                    "ecosystem_uid": d["ecosystem_uid"],
                    "status": d["status"],
                    "mode": d["mode"],
                    "method": d["method"],
                    "morning_start": morning_start,
                    "morning_end": morning_end,
                    "evening_start": evening_start,
                    "evening_end": evening_end
                }
                await api.light.update_or_create(session, light_info=light_info)
        await self.emit("light_data", data, namespace="/")


'''
# ---------------------------------------------------------------------------
#   Dispatcher socketio
# ---------------------------------------------------------------------------
@dispatcher.on("turn_light")
async def _turn_light(*args, **kwargs):
    await sio_manager.emit("turn_light", namespace="/gaia", **kwargs)


@dispatcher.on("turn_actuator")
async def _turn_actuator(*args, **kwargs):
    await sio_manager.emit("turn_actuator", namespace="/gaia", **kwargs)
'''
