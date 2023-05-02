from __future__ import annotations

from asyncio import sleep
from datetime import datetime, time, timezone
import logging
import random
from typing import cast, TypedDict

import cachetools
from dispatcher import AsyncDispatcher, AsyncEventHandler
from socketio import AsyncNamespace
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from gaia_validators import (
    BaseInfoConfigPayloadDict, EnvironmentConfigPayloadDict, HealthDataPayloadDict,
    LightDataPayloadDict, HardwareConfigPayloadDict, ManagementConfigPayloadDict,
    ManagementFlags, SensorsDataPayloadDict
)
from ouranos import current_app, db
from ouranos.aggregator.decorators import (
    dispatch_to_application, registration_required
)
from ouranos.core.cache import SensorDataCache
from ouranos.core.database.models.gaia import (
    Ecosystem, Engine, EnvironmentParameter, Hardware, HealthRecord, Light,
    SensorRecord
)
from ouranos.core.utils import decrypt_uid, humanize_list, validate_uid_token


class SensorDataRecord(TypedDict):
    ecosystem_uid: str
    sensor_uid: str
    measure: str
    timestamp: datetime
    value: float


_ecosystem_name_cache: dict[str, str] = {}


async def get_ecosystem_name(
        ecosystem_uid: str,
        session: AsyncSession | None = None
) -> str:
    try:
        return _ecosystem_name_cache[ecosystem_uid]
    except KeyError:
        if session is not None:
            ecosystem_obj = await Ecosystem.get(session, ecosystem_uid)
            if ecosystem_obj is not None:
                _ecosystem_name_cache[ecosystem_uid] = ecosystem_obj.name
                return ecosystem_obj.name
        async with db.scoped_session() as session:
            ecosystem_obj = await Ecosystem.get(session, ecosystem_uid)
            if ecosystem_obj is not None:
                _ecosystem_name_cache[ecosystem_uid] = ecosystem_obj.name
                return ecosystem_obj.name
        # TODO: return or raise when not found


def try_time_from_iso(iso_str: str | None) -> time | None:
    try:
        return time.fromisoformat(iso_str)
    except (TypeError, AttributeError):
        return None


def try_datetime_from_iso(iso_str: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(iso_str).astimezone(timezone.utc)
    except (TypeError, AttributeError):
        return None


class Events:
    broker_type: str = "raw"

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._background_task_started: bool = False
        self.engines_blacklist = cachetools.TTLCache(maxsize=62, ttl=60 * 60 * 24)
        self.logger = logging.getLogger("ouranos.aggregator")
        self._ouranos_dispatcher: AsyncDispatcher | None = None

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

    @property
    def ouranos_dispatcher(self) -> AsyncDispatcher:
        if not self._ouranos_dispatcher:
            raise RuntimeError("You need to set dispatcher")
        return self._ouranos_dispatcher

    @ouranos_dispatcher.setter
    def ouranos_dispatcher(self, dispatcher: AsyncDispatcher):
        self._ouranos_dispatcher = dispatcher
        self.ouranos_dispatcher.on("turn_light", self.turn_light)
        self.ouranos_dispatcher.on("turn_actuator", self.turn_actuator)
        self.ouranos_dispatcher.on("crud", self.crud)
        self.ouranos_dispatcher.start()

    async def gaia_background_task(self):
        pass

    # ---------------------------------------------------------------------------
    #   Events Gaia <-> Aggregator
    # ---------------------------------------------------------------------------
    async def on_connect(self, sid, environ):
        # if not self._background_task_started:
        #     asyncio.ensure_future(self.gaia_background_task())
        #     self._background_task_started = True
        if self.broker_type == "socketio":
            async with self.session(sid, namespace="/gaia") as session:
                remote_addr = session["REMOTE_ADDR"] = environ["REMOTE_ADDR"]
                self.logger.debug(f"Received a connection from {remote_addr}")
                attempts = self.engines_blacklist.get(remote_addr, 0)
                max_attempts: int = current_app.config.get("GAIA_CLIENT_MAX_ATTEMPT", 2)
                if attempts == max_attempts:
                    self.logger.warning(
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
        elif self.broker_type == "dispatcher":
            self.logger.debug(f"Connected to the message broker")
            await self.emit("register", ttl=2)
        else:
            raise TypeError("Event broker_type is invalid")

    async def on_disconnect(self, sid, *args) -> None:
        async with db.scoped_session() as session:
            engine = await Engine.get(session, engine_id=sid)
            if engine is None:
                return
            uid = engine.uid
            self.leave_room(sid, "engines", namespace="/gaia")
            await self.ouranos_dispatcher.emit(
                "ecosystem_status",
                {ecosystem.uid: {"status": ecosystem.status, "connected": False}
                 for ecosystem in engine.ecosystems},
                namespace="application"
            )
            self.logger.info(f"Engine {uid} disconnected")

    async def on_register_engine(self, sid, data) -> None:
        validated = False
        remote_addr: str
        if self.broker_type == "socketio":
            async with self.session(sid) as session:
                remote_addr = session["REMOTE_ADDR"]
                engine_uid = decrypt_uid(data["ikys"])
                if validate_uid_token(data["uid_token"], engine_uid):
                    session["engine_uid"] = engine_uid
                    self.logger.debug(
                        f"Received 'register_engine' from engine {engine_uid}"
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
                    self.logger.info(
                        f"Received invalid registration request from {remote_addr}")
                    validated = False
                    await self.disconnect(sid)
        elif self.broker_type == "dispatcher":
            engine_uid = data.get("engine_uid")
            self.logger.debug(
                f"Received 'register_engine' from engine {engine_uid}"
            )
            if engine_uid:
                async with self.session(sid) as session:
                    session["engine_uid"] = engine_uid
                remote_addr = data.get("address", "")
                validated = True
            else:
                await self.disconnect(sid)
        else:
            raise TypeError("Event broker_type is invalid")
        if validated:
            now = datetime.now(timezone.utc).replace(microsecond=0)
            engine_info = {
                "uid": engine_uid,
                "sid": sid,
                "registration_date": now,
                "last_seen": now,
                "address": f"{remote_addr}",
            }
            async with db.scoped_session() as session:
                await Engine.update_or_create(session, engine_info)
            self.enter_room(sid, room="engines", namespace="/gaia")
            if self.broker_type == "socketio":
                await self.emit("register_ack", namespace="/gaia", room=sid)
            elif self.broker_type == "dispatcher":
                await self.emit("register_ack", namespace="/gaia", room=sid, ttl=15)
            self.logger.info(f"Successful registration of engine {engine_uid}")

    @registration_required
    async def on_ping(self, sid, data, engine_uid) -> None:
        self.logger.debug(f"Received 'ping' from engine {engine_uid}")
        now = datetime.now(timezone.utc).replace(microsecond=0)
        ecosystems_seen: list[str] = []
        async with db.scoped_session() as session:
            engine = await Engine.get(session, sid)
            if engine:
                engine.last_seen = now
                for ecosystem_uid in data:
                    ecosystem = await Ecosystem.get(session, ecosystem_uid)
                    if ecosystem is not None:
                        ecosystems_seen.append(ecosystem.name)
                        ecosystem.last_seen = now
        self.logger.debug(
            f"Updated last seen info for ecosystem(s) "
            f"{humanize_list(ecosystems_seen)}"
        )

    @registration_required
    async def on_base_info(
            self,
            sid: str,
            data: list[BaseInfoConfigPayloadDict],
            engine_uid: str
    ) -> None:
        self.logger.debug(f"Received 'base_info' from engine: {engine_uid}")
        ecosystems: list[dict[str, str]] = []
        ecosystems_to_log: list[str] = []
        async with db.scoped_session() as session:
            for payload in data:
                ecosystem = payload["data"]
                ecosystems_to_log.append(ecosystem["name"])
                await Ecosystem.update_or_create(session, ecosystem)
            ecosystems.append({"uid": payload["uid"], "status": ecosystem["status"]})
        self.logger.debug(
            f"Logged base info from ecosystem(s): {humanize_list(ecosystems_to_log)}"
        )
        await self.ouranos_dispatcher.emit(
            "ecosystem_status",
            data=ecosystems,
            namespace="application"
        )

    @registration_required
    async def on_management(
            self,
            sid: str,
            data: list[ManagementConfigPayloadDict],
            engine_uid: str
    ) -> None:
        self.logger.debug(f"Received 'management' from engine: {engine_uid}")
        ecosystems_to_log: list[str] = []
        async with db.scoped_session() as session:
            for payload in data:
                ecosystem = payload["data"]
                uid: str = payload["uid"]
                ecosystems_to_log.append(
                    await get_ecosystem_name(uid, session=session)
                )
                ecosystem_obj = await Ecosystem.get(session, uid)
                for management in ManagementFlags:
                    try:
                        if ecosystem[management.name]:
                            ecosystem_obj.add_management(management)
                    except KeyError:
                        # Not implemented in gaia yet
                        pass
                session.add(ecosystem_obj)
                await sleep(0)
        self.logger.debug(
            f"Logged management info from ecosystem(s): "
            f"{humanize_list(ecosystems_to_log)}"
        )

    @registration_required
    async def on_environmental_parameters(
            self,
            sid: str,
            data: list[EnvironmentConfigPayloadDict],
            engine_uid: str
    ) -> None:
        self.logger.debug(
            f"Received 'environmental_parameters' from engine: {engine_uid}"
        )
        ecosystems_to_log: list[str] = []
        async with db.scoped_session() as session:
            for payload in data:
                uid: str = payload["uid"]
                ecosystems_to_log.append(
                    await get_ecosystem_name(uid, session=session)
                )
                ecosystem = payload["data"]
                sky = ecosystem["sky"]
                ecosystem_info = {
                    "uid": uid,
                    "day_start": try_time_from_iso(sky.get("day")),
                    "night_start": try_time_from_iso(sky.get("night")),
                }
                await Ecosystem.update_or_create(session, ecosystem_info)
                await Light.update_or_create(
                    session, {"method": sky.get("lighting")}, uid)
                for param in ecosystem["climate"]:
                    await EnvironmentParameter.update_or_create(
                        session, param, uid)
        self.logger.debug(
            f"Logged environmental parameters from ecosystem(s): "
            f"{humanize_list(ecosystems_to_log)}"
        )

    @registration_required
    async def on_hardware(
            self,
            sid: str,
            data: list[HardwareConfigPayloadDict],
            engine_uid: str
    ) -> None:
        self.logger.debug(
            f"Received 'hardware' from engine: {engine_uid}"
        )
        ecosystems_to_log: list[str] = []
        async with db.scoped_session() as session:
            active_hardware = []
            for payload in data:
                uid = payload["uid"]
                ecosystems_to_log.append(
                    await get_ecosystem_name(uid, session=session)
                )
                for hardware in payload["data"]:
                    hardware_uid = hardware.pop("uid")
                    active_hardware.append(hardware_uid)
                    hardware["ecosystem_uid"] = uid
                    # TODO: register multiplexer ?
                    del hardware["multiplexer_model"]
                    await Hardware.update_or_create(
                        session, values=hardware, uid=hardware_uid,)
                    await sleep(0)
            stmt = select(Hardware).where(Hardware.uid.not_in(active_hardware))
            result = await session.execute(stmt)
            inactive = result.scalars().all()
            for hardware in inactive:
                hardware.status = False
        self.logger.debug(
            f"Logged hardware info from ecosystem(s): {humanize_list(ecosystems_to_log)}"
        )

    # --------------------------------------------------------------------------
    #   Events Gaia -> Aggregator -> Api
    # --------------------------------------------------------------------------
    @registration_required
    async def on_sensors_data(
            self,
            sid: str,
            data: list[SensorsDataPayloadDict],
            engine_uid: str
    ) -> None:
        self.logger.debug(
            f"Received 'sensors_data' from engine: {engine_uid}"
        )
        SensorDataCache.update({
            payload["uid"]: payload["data"] for payload in data
        })
        await self.ouranos_dispatcher.emit(
            "current_sensors_data", data=data, namespace="application", ttl=15)
        ecosystems_updated: list[str] = [payload["uid"] for payload in data]
        if ecosystems_updated:
            self.logger.debug(
                f"Updated `sensors_data` cache with data from ecosystem(s) "
                f"{humanize_list(ecosystems_updated)}"
            )
        values: list[dict] = []
        logged: list[str] = []
        for payload in data:
            sensor_uids_seen: list[str] = []
            ecosystem = payload["data"]
            dt = try_datetime_from_iso(ecosystem.get("timestamp"))
            if dt is None:
                continue
            if dt.minute % current_app.config["SENSOR_LOGGING_PERIOD"] == 0:
                logged.append(
                    await get_ecosystem_name(payload["uid"], session=None)
                )
                for sensor in ecosystem["records"]:
                    sensor_uid: str = sensor["sensor_uid"]
                    sensor_uids_seen.append(sensor_uid)
                    for measure in sensor["measures"]:
                        sensor_data = {
                            "ecosystem_uid": payload["uid"],
                            "sensor_uid": sensor_uid,
                            "measure": measure["measure"],
                            "timestamp": dt,
                            "value": float(measure["value"]),
                        }
                        values.append(sensor_data)
                    await sleep(0)
                async with db.scoped_session() as session:
                    hardware_list = await Hardware.get_multiple(
                        session, sensor_uids_seen)
                    for hardware in hardware_list:
                        hardware.last_log = dt
                # TODO: if needed get and log avg values from the data
        if values:
            async with db.scoped_session() as session:
                await SensorRecord.create_records(session, values)
            self.logger.debug(
                f"Logged sensors data from ecosystem(s) "
                f"{humanize_list(logged)}"
            )

    @registration_required
    @dispatch_to_application
    async def on_health_data(
            self,
            sid: str,
            data: list[HealthDataPayloadDict],
            engine_uid: str
    ) -> None:
        self.logger.debug(
            f"Received 'update_health_data' from {engine_uid}"
        )
        logged: list[str] = []
        # healthData.update(data)
        values: list[dict] = []
        for payload in data:
            ecosystem = payload["data"]
            logged.append(
                await get_ecosystem_name(payload["uid"], session=None)
            )
            health_data = {
                "ecosystem_uid": payload["uid"],
                "timestamp": datetime.fromisoformat(ecosystem["timestamp"]),
                "green": ecosystem["green"],
                "necrosis": ecosystem["necrosis"],
                "health_index": ecosystem["index"]
            }
            values.append(health_data)
        if values:
            async with db.scoped_session() as session:
                await HealthRecord.create_records(session, values)
            self.logger.debug(
                f"Logged health data from ecosystem(s): "
                f"{humanize_list(logged)}"
            )

    @registration_required
    @dispatch_to_application
    async def on_light_data(
            self,
            sid: str,
            data: list[LightDataPayloadDict],
            engine_uid: str
    ) -> None:
        self.logger.debug(f"Received 'light_data' from {engine_uid}")
        ecosystems_to_log: list[str] = []
        async with db.scoped_session() as session:
            for payload in data:
                ecosystems_to_log.append(
                    await get_ecosystem_name(payload["uid"], session)
                )
                ecosystem = payload["data"]
                morning_start = try_time_from_iso(
                    cast(str, ecosystem.get("morning_start")))
                morning_end = try_time_from_iso(
                    cast(str,ecosystem.get("morning_end", None)))
                evening_start = try_time_from_iso(
                    cast(str, ecosystem.get("evening_start", None)))
                evening_end = try_time_from_iso(
                    cast(str, ecosystem.get("evening_end", None)))
                light_info = {
                    "ecosystem_uid": payload["uid"],
                    "status": ecosystem["status"],
                    "mode": ecosystem["mode"],
                    "method": ecosystem["method"],
                    "morning_start": morning_start,
                    "morning_end": morning_end,
                    "evening_start": evening_start,
                    "evening_end": evening_end
                }
                await Light.update_or_create(session, light_info)
        self.logger.debug(
            f"Logged light data from ecosystem(s): {humanize_list(ecosystems_to_log)}"
        )

    # ---------------------------------------------------------------------------
    #   Events Api -> Aggregator -> Gaia
    # ---------------------------------------------------------------------------
    async def _turn_actuator(self, sid, data) -> None:
        if self.broker_type == "socketio":
            await self.emit(
                "turn_actuator", data=data, namespace="/gaia", room=sid)
        elif self.broker_type == "dispatcher":
            await self.emit(
                "turn_actuator", data=data, namespace="/gaia", room=sid, ttl=30)
        else:
            raise TypeError("Event broker_type is invalid")

    async def turn_light(self, sid, data) -> None:
        data["actuator"] = "light"
        await self._turn_actuator(sid, data)

    async def turn_actuator(self, sid, data) -> None:
        await self._turn_actuator(sid, data)

    async def crud(self, sid, data) -> None:
        if self.broker_type == "socketio":
            await self.emit(
                "crud", data=data, namespace="/gaia", room=sid)
        elif self.broker_type == "dispatcher":
            await self.emit(
                "crud", data=data, namespace="/gaia", room=sid, ttl=30)
        else:
            raise TypeError("Event broker_type is invalid")


class DispatcherBasedGaiaEvents(AsyncEventHandler, Events):
    broker_type = "dispatcher"

    def __init__(self) -> None:
        super().__init__(namespace="/gaia")


class SioBasedGaiaEvents(AsyncNamespace, Events):
    broker_type = "socketio"

    def __init__(self) -> None:
        super().__init__(namespace="/gaia")
