from __future__ import annotations

import asyncio
from asyncio import sleep
from datetime import datetime, time, timezone
import logging
import random
import typing as t

import cachetools

from .decorators import dispatch_to_clients, registration_required
from src.core import api
from src.core.g import config, db
from src.core.utils import decrypt_uid, validate_uid_token


def try_time_from_iso(iso_str: str) -> t.Optional[time]:
    try:
        return time.fromisoformat(iso_str)
    except (TypeError, AttributeError):
        return None


class Events:
    type: str = "raw"

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._background_task_started: bool = False
        self.engines_blacklist = cachetools.TTLCache(maxsize=62, ttl=60 * 60 * 24)
        app_name = config['APP_NAME'].lower()
        self.collector_logger = logging.getLogger(f"{app_name}.collector")
        self.broker_logger = logging.getLogger(f"{app_name}.broker")

    @property
    def to_clients(self) -> str:
        if self.type == "socketio":
            return "/"
        else:
            return "application"

    async def emit(
            self,
            event: str,
            data=None,
            to=None,
            room=None,
            namespace=None,
            **kwargs
    ) -> None:
        raise NotImplementedError

    async def session(self, sid: str, namespace: str | None = None) -> None:
        raise NotImplementedError

    def enter_room(self, sid: str, room: str, namespace: str | None = None) -> None:
        raise NotImplementedError

    def leave_room(self, sid: str, room: str, namespace: str | None = None) -> None:
        raise NotImplementedError

    async def disconnect(self, sid: str, namespace: str | None = None) -> None:
        raise NotImplementedError

    async def gaia_background_task(self):
        """while True:
            await self.emit("ping", namespace="/gaia", room="engines")
            await sleep(15)"""

    # ---------------------------------------------------------------------------
    #   Events coming from Gaia instances
    # ---------------------------------------------------------------------------
    async def on_connect(self, sid, environ):
        if not self._background_task_started:
            asyncio.ensure_future(self.gaia_background_task())
            self._background_task_started = True
        if self.type == "socketio":
            async with self.session(sid, namespace="/gaia") as session:
                remote_addr = session["REMOTE_ADDR"] = environ["REMOTE_ADDR"]
                attempts = self.engines_blacklist.get(remote_addr, 0)
                max_attempts: int = config.get("GAIA_CLIENT_MAX_ATTEMPT", 2)
                if attempts == max_attempts:
                    self.broker_logger.warning(
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
                    try:
                        self.engines_blacklist[remote_addr] += 1
                    except KeyError:
                        pass
                    return False
        elif self.type == "dispatcher":
            await self.emit("register", ttl=30)
        else:
            raise TypeError("Event type is invalid")

    async def on_disconnect(self, sid, *args):
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
                namespace=self.to_clients
            )
            self.broker_logger.info(f"Engine {uid} disconnected")

    @registration_required
    async def on_ping(self, sid, data, engine_uid):
        self.broker_logger.debug(f"Received 'ping' from engine: {engine_uid}")
        now = datetime.now(timezone.utc).replace(microsecond=0)
        async with db.scoped_session() as session:
            engine = await api.engine.get(session, sid)
            if engine:
                engine.last_seen = now
                for ecosystem_uid in data:
                    self.collector_logger.debug(
                        f"Updating last seen info for ecosystem: "
                        f"{ecosystem['ecosystem_uid']}"
                    )
                    ecosystem = await api.ecosystem.get(session, ecosystem_uid)
                    ecosystem.last_seen = now

    async def on_register_engine(self, sid, data):
        if self.type == "socketio":
            async with self.session(sid) as session:
                remote_addr = session["REMOTE_ADDR"]
                engine_uid = decrypt_uid(data["ikys"])
                if validate_uid_token(data["uid_token"], engine_uid):
                    session["engine_uid"] = engine_uid
                    self.broker_logger.debug(
                        f"Received 'register_engine' from engine: {engine_uid}"
                    )
                    validated = True
                    try:
                        del self.engines_blacklist[remote_addr]
                    except KeyError:
                        pass
                else:
                    try:
                        self.engines_blacklist[remote_addr] += 1
                    except KeyError:
                        self.engines_blacklist[remote_addr] = 0
                    self.broker_logger.info(
                        f"Received invalid registration request from {remote_addr}")
                    validated = False
                    await self.disconnect(sid)
        elif self.type == "dispatcher":
            async with self.session(sid) as session:
                engine_uid = data.get("engine_uid")
                self.broker_logger.debug(
                    f"Received 'register_engine' from engine: {engine_uid}"
                )
                if engine_uid:
                    session["engine_uid"] = engine_uid
                    validated = True
                else:
                    await self.disconnect(sid)
        else:
            raise TypeError("Event type is invalid")
        if validated:
            now = datetime.now(timezone.utc).replace(microsecond=0)
            engine_info = {
                "uid": engine_uid,
                "sid": sid,
                "registration_date": now,
                "last_seen": now,
                # "address": f"{remote_addr}",
            }
            async with db.scoped_session() as session:
                await api.engine.update_or_create(session, engine_info)
            self.enter_room(sid, room="engines", namespace="/gaia")
            await self.emit("register_ack", namespace="/gaia", room=sid)
            self.broker_logger.info(f"Successful registration of engine {engine_uid}")

    @registration_required
    async def on_base_info(self, sid, data, engine_uid):
        self.broker_logger.debug(f"Received 'base_info' from engine: {engine_uid}")
        ecosystems: list[dict[str, str]] = []
        for ecosystem in data:
            ecosystem.update({"engine_uid": engine_uid})
            uid: str = ecosystem["uid"]
            async with db.scoped_session() as session:
                self.collector_logger.debug(
                    f"Logging base info from ecosystem: "
                    f"{ecosystem['ecosystem_uid']}"
                )
                await api.ecosystem.update_or_create(session, ecosystem)
            ecosystems.append({"uid": uid, "status": ecosystem["status"]})
        await self.emit(
            "ecosystem_status",
            data=ecosystems,
            namespace=self.to_clients
        )

    @registration_required
    async def on_management(self, sid, data, engine_uid):
        self.broker_logger.debug(f"Received 'management' from engine: {engine_uid}")
        async with db.scoped_session() as session:
            for ecosystem in data:
                self.collector_logger.debug(
                    f"Logging management info from ecosystem: "
                    f"{ecosystem['ecosystem_uid']}"
                )
                uid: str = ecosystem["uid"]
                ecosystem = await api.ecosystem.update_or_create(session, uid=uid)
                for m, v in api.Management.items():
                    try:
                        if ecosystem[m]:
                            ecosystem.add_management(v)
                    except KeyError:
                        # Not implemented in gaia yet
                        pass
                session.add(ecosystem)
                await sleep(0)

    @registration_required
    async def on_environmental_parameters(self, sid, data, engine_uid):
        self.broker_logger.debug(
            f"Received 'environmental_parameters' from engine: {engine_uid}"
        )
        async with db.scoped_session() as session:
            for ecosystem in data:
                self.collector_logger.debug(
                    f"Logging environmental parameters from ecosystem: "
                    f"{ecosystem['ecosystem_uid']}"
                )
                uid: str = ecosystem["uid"]
                ecosystem["engine_uid"] = engine_uid
                tods = {}
                env_params = {}
                for tod in ["day", "night"]:
                    params = ecosystem.get(tod)
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
                        {"hysteresis": ecosystem.get("hysteresis", {}).get(param)}
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
                    session, light_info={"method": ecosystem.get("light")},
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
        self.broker_logger.debug(
            f"Received 'hardware' from engine: {engine_uid}"
        )
        async with db.scoped_session() as session:
            for ecosystem in data:
                self.collector_logger.debug(
                    f"Logging hardware info from ecosystem: "
                    f"{ecosystem['ecosystem_uid']}"
                )
                uid = ecosystem.pop("uid")
                for hardware_uid, hardware_dict in ecosystem.items():
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
                                break  # TODO: fix this
                                if m not in hardware.measure:
                                    hardware.measure.append(m)
                    if plants:
                        if isinstance(plants, str):
                            plants = [plants]
                        _plants = await api.plant.get_multiple(session, plants)
                        if _plants:
                            for p in _plants:
                                break  # TODO: fix this
                                if p not in hardware.plants:
                                    hardware.plants.append(m)
                    session.add(hardware)
                    await sleep(0)

    # --------------------------------------------------------------------------
    #   Data received from Gaia, required to be redispatched and logged
    # --------------------------------------------------------------------------
    @registration_required
    @dispatch_to_clients
    async def on_sensors_data(self, sid, data, engine_uid):
        self.broker_logger.debug(
            f"Received 'sensors_data' from engine: {engine_uid}"
        )
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
        async with db.scoped_session() as session:
            values: list[dict] = []
            for ecosystem in data:
                dt_str: str = ecosystem.get("datetime")
                if not dt_str:
                    continue
                dt = datetime.fromisoformat(dt_str)
                if dt.minute % config["SENSORS_LOGGING_PERIOD"] == 0:
                    self.collector_logger.debug(
                        f"Logging sensors data from ecosystem: "
                        f"{ecosystem['ecosystem_uid']}"
                    )
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
                            values.append(sensor_data)
                        await sleep(0)
                    # TODO: if needed get and log avg values from the data
            if values:
                await api.sensor.create_records(session, values)

    @registration_required
    @dispatch_to_clients
    async def on_health_data(self, sid, data, engine_uid):
        self.broker_logger.debug(
            f"Received 'update_health_data' from {engine_uid}"
        )
        # dispatcher.emit("application", "health_data", data=data)
        # healthData.update(data)
        async with db.scoped_session() as session:
            values: list[dict] = []
            for ecosystem in data:
                self.collector_logger.debug(
                    f"Logging health data from ecosystem: "
                    f"{ecosystem['ecosystem_uid']}"
                )
                health_data = {
                    "ecosystem_uid": ecosystem["ecosystem_uid"],
                    "datetime": datetime.fromisoformat(ecosystem["datetime"]),
                    "green": ecosystem["green"],
                    "necrosis": ecosystem["necrosis"],
                    "health_index": ecosystem["health_index"]
                }
                values.append(health_data)
            await api.health.create_records(session, values)

    @registration_required
    @dispatch_to_clients
    async def on_light_data(self, sid, data, engine_uid):
        self.broker_logger.debug(f"Received 'light_data' from {engine_uid}")
        async with db.scoped_session() as session:
            for ecosystem in data:
                self.collector_logger.debug(
                    f"Logging light data from ecosystem: "
                    f"{ecosystem['ecosystem_uid']}"
                )
                morning_start = try_time_from_iso(
                    ecosystem.get("morning_start", None))
                morning_end = try_time_from_iso(
                    ecosystem.get("morning_end", None))
                evening_start = try_time_from_iso(
                    ecosystem.get("evening_start", None))
                evening_end = try_time_from_iso(
                    ecosystem.get("evening_end", None))
                light_info = {
                    "ecosystem_uid": ecosystem["ecosystem_uid"],
                    "status": ecosystem["status"],
                    "mode": ecosystem["mode"],
                    "method": ecosystem["method"],
                    "morning_start": morning_start,
                    "morning_end": morning_end,
                    "evening_start": evening_start,
                    "evening_end": evening_end
                }
                await api.light.update_or_create(session, light_info=light_info)


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
