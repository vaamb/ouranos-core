from __future__ import annotations

from asyncio import sleep
from datetime import datetime, timezone
import logging
import random
from typing import cast, TypedDict

from cachetools import LRUCache, TTLCache
from dispatcher import AsyncDispatcher, AsyncEventHandler
from pydantic import BaseModel, parse_obj_as
from socketio import AsyncNamespace
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from gaia_validators import *
from ouranos import current_app, db
from ouranos.aggregator.decorators import (
    dispatch_to_application, registration_required)
from ouranos.core.database.models.gaia import (
    Ecosystem, Engine, EnvironmentParameter, Hardware, HealthRecord, Light,
    SensorRecord)
from ouranos.core.database.models.memory import SensorDbCache
from ouranos.core.utils import decrypt_uid, humanize_list, validate_uid_token


_ecosystem_name_cache = LRUCache(maxsize=32)


class SensorDataRecord(TypedDict):
    ecosystem_uid: str
    sensor_uid: str
    measure: str
    timestamp: datetime
    value: float


class SocketIOEnginePayload(EnginePayload):
    ikys: str | None = None
    uid_token: str | None = None


class SocketIOEnginePayloadDict(EnginePayloadDict):
    ikys: str | None
    uid_token: str | None


def validate_payload(data: list[dict], model_cls: BaseModel) -> list[dict]:
    temp: list[BaseModel] = parse_obj_as(list[model_cls], data)
    return [obj.dict() for obj in temp]


async def get_ecosystem_name(
        ecosystem_uid: str,
        session: AsyncSession | None = None
) -> str:
    try:
        return _ecosystem_name_cache[ecosystem_uid]
    except KeyError:
        async def inner_func(session: AsyncSession, ecosystem_uid: str):
            ecosystem_obj = await Ecosystem.get(session, ecosystem_uid)
            if ecosystem_obj is not None:
                _ecosystem_name_cache[ecosystem_uid] = ecosystem_obj.name
                return ecosystem_obj.name

        if session is not None:
            return await inner_func(session, ecosystem_uid)
        async with db.scoped_session() as session:
            return await inner_func(session, ecosystem_uid)
        # TODO: return or raise when not found


class Events:
    broker_type: str = "raw"

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._background_task_started: bool = False
        self.engines_blacklist = TTLCache(maxsize=62, ttl=60 * 60 * 24)
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

    async def on_register_engine(self, sid, data: SocketIOEnginePayloadDict) -> None:
        data: SocketIOEnginePayloadDict = SocketIOEnginePayload(**data).dict()
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
                remote_addr = data["address"]
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
    async def on_ping(self, sid, data: list[str], engine_uid) -> None:
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
        data: list[BaseInfoConfigPayloadDict] = validate_payload(
            data, BaseInfoConfigPayload)
        ecosystems: list[dict[str, str]] = []
        ecosystems_to_log: list[str] = []
        async with db.scoped_session() as session:
            for payload in data:
                ecosystem = payload["data"]
                ecosystem["last_seen"] = datetime.now(timezone.utc)
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
        data: list[ManagementConfigPayloadDict] = validate_payload(
            data, ManagementConfigPayload)
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
        data: list[EnvironmentConfigPayloadDict] = validate_payload(
            data, EnvironmentConfigPayload)
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
                    "day_start": sky["day"],
                    "night_start": sky["night"],
                }
                await Ecosystem.update_or_create(session, ecosystem_info)
                await Light.update_or_create(
                    session, {"method": sky["lighting"]}, uid)
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
        data: list[HardwareConfigPayloadDict] = validate_payload(
            data, HardwareConfigPayload)
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
                        session, values=hardware, uid=hardware_uid)
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
        data: list[SensorsDataPayloadDict] = validate_payload(
            data, SensorsDataPayload)
        await self.ouranos_dispatcher.emit(
            "current_sensors_data", data=data, namespace="application", ttl=15)
        sensors_data: list[SensorDataRecord] = []
        last_log: dict[str, datetime] = {}
        for ecosystem in data:
            ecosystem_data = ecosystem["data"]
            for sensor_record in ecosystem_data["records"]:
                sensor_uid: str = sensor_record["sensor_uid"]
                last_log[sensor_uid] = ecosystem_data["timestamp"]
                for measure in sensor_record["measures"]:
                    sensors_data.append(cast(SensorDataRecord, {
                        "ecosystem_uid": ecosystem["uid"],
                        "sensor_uid": sensor_record["sensor_uid"],
                        "measure": measure["measure"],
                        "timestamp": ecosystem_data["timestamp"],
                        "value": float(measure["value"]),
                    }))
            await sleep(0)
        if not sensors_data:
            return
        async with db.scoped_session() as session:
            # Send all data to temp database
            await SensorDbCache.insert_data(session, sensors_data)
            await session.commit()
            hardware_uids = [*{s["sensor_uid"] for s in sensors_data}]
            self.logger.debug(
                f"Updated `sensors_data` cache with data from sensors "
                f"{humanize_list(hardware_uids)}"
            )

            # Send data to records database if SENSOR_LOGGING_PERIOD requires it
            logging_period = current_app.config["SENSOR_LOGGING_PERIOD"]
            sensors_data = [
                s for s in sensors_data
                if (
                    logging_period and
                    s["timestamp"].minute % logging_period == 0
                )
            ]
            if not sensors_data:
                return
            await SensorRecord.create_records(session, sensors_data)
            # Update the last_log column for hardware
            hardware_uids = [*{s["sensor_uid"] for s in sensors_data}]
            for hardware in await Hardware.get_multiple(session, hardware_uids):
                hardware.last_log = last_log.get(hardware.uid)
            await session.commit()
            # Get ecosystem IDs
            ecosystems = await Ecosystem.get_multiple(
                session, [payload["uid"] for payload in data])
            self.logger.debug(
                f"Logged sensors data from ecosystem(s) "
                f"{humanize_list([e.name for e in ecosystems])}"
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
        data: list[HealthDataPayloadDict] = validate_payload(
            data, HealthDataPayload)
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
        data: list[LightDataPayloadDict] = validate_payload(
            data, LightDataPayload)
        ecosystems_to_log: list[str] = []
        async with db.scoped_session() as session:
            for payload in data:
                ecosystems_to_log.append(
                    await get_ecosystem_name(payload["uid"], session)
                )
                ecosystem = payload["data"]
                light_info = {
                    "ecosystem_uid": payload["uid"],
                    "status": ecosystem["status"],
                    "mode": ecosystem["mode"],
                    "method": ecosystem["method"],
                    "morning_start": ecosystem["morning_start"],
                    "morning_end": ecosystem["morning_end"],
                    "evening_start": ecosystem["evening_start"],
                    "evening_end": ecosystem["evening_end"]
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
