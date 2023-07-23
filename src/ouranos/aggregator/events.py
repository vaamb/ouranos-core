from __future__ import annotations

from asyncio import sleep
from datetime import datetime, timezone
import inspect
import logging
import random
from typing import cast, overload, Type, TypedDict
from uuid import UUID

from cachetools import LRUCache, TTLCache
from pydantic import TypeAdapter, ValidationError
from socketio import AsyncNamespace
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from dispatcher import AsyncDispatcher, AsyncEventHandler
from gaia_validators import *
from gaia_validators import (
    HealthRecord as gvHealthRecord, SensorRecord as gvSensorRecord)

from ouranos import current_app, db, json
from ouranos.aggregator.decorators import (
    dispatch_to_application, registration_required)
from ouranos.core.database.models.gaia import (
    ActuatorStatus, CrudRequest, Ecosystem, Engine, EnvironmentParameter,
    Hardware, HealthRecord, Lighting, Measure, SensorRecord)
from ouranos.core.database.models.memory import SensorDbCache
from ouranos.core.utils import decrypt_uid, humanize_list, validate_uid_token


_ecosystem_name_cache = LRUCache(maxsize=32)
_ecosystem_sid_cache = LRUCache(maxsize=32)


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


async def get_engine_sid(
        engine_uid: str,
        session: AsyncSession | None = None
) -> str:
    try:
        return _ecosystem_sid_cache[engine_uid]
    except KeyError:
        async def inner_func(session: AsyncSession, engine_uid: str):
            engine_obj = await Engine.get(session, engine_uid)
            if engine_obj is not None:
                sid = engine_obj.sid
                _ecosystem_sid_cache[engine_uid] = sid
                return sid

        if session is not None:
            return await inner_func(session, engine_uid)
        async with db.scoped_session() as session:
            return await inner_func(session, engine_uid)


class Events:
    broker_type: str = "raw"

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._background_task_started: bool = False
        self.engines_blacklist = TTLCache(maxsize=64, ttl=60 * 60 * 24)
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

    async def gaia_background_task(self):
        pass

    @overload
    def validate_payload(
            self,
            data: dict,
            model_cls: Type[BaseModel],
            type_=dict
    ) -> dict:
        ...

    @overload
    def validate_payload(
            self,
            data: list[dict],
            model_cls: Type[BaseModel],
            type_=list[dict]
    ) -> list[dict]:
        ...

    def validate_payload(
            self,
            data: dict | list[dict],
            model_cls: Type[BaseModel],
            type_: Type
    ) -> dict | list[dict]:
        if not data:
            event = inspect.stack()[1].function.lstrip("on_")
            self.logger.error(
                f"Encountered an error while validating '{event}' data. Error "
                f"msg: Empty data."
            )
            raise ValidationError
        if not isinstance(data, type_):
            event = inspect.stack()[1].function.lstrip("on_")
            received = type(data)
            self.logger.error(
                f"Encountered an error while validating '{event}' data. Error "
                f"msg: Wrong data format, expected '{type_}', received "
                f"'{received}'."
            )
            raise ValidationError
        try:
            if type_ == list:
                temp: list[BaseModel] = TypeAdapter(list[model_cls]).validate_python(data)
                return [obj.model_dump() for obj in temp]
            elif type_ == dict:
                return model_cls(**data).model_dump()
        except ValidationError as e:
            event = inspect.stack()[1].function.lstrip("on_")
            msg_list = [f"{error['loc'][0]}: {error['msg']}" for error in e.errors()]
            self.logger.error(
                f"Encountered an error while validating '{event}' data. Error "
                f"msg: {', '.join(msg_list)}"
            )
            raise

    # ---------------------------------------------------------------------------
    #   Events Gaia <-> Aggregator
    # ---------------------------------------------------------------------------
    async def on_connect(self, sid, environ):
        if self.broker_type == "socketio":
            async with self.session(sid, namespace="/gaia") as session:
                remote_addr = session["REMOTE_ADDR"] = environ["REMOTE_ADDR"]
            self.logger.debug(f"Received a connection from {remote_addr}")
            await self.emit("register")
        elif self.broker_type == "dispatcher":
            self.logger.info(f"Connected to the message broker")
            await self.emit("register", ttl=75)

    async def on_disconnect(self, sid, *args) -> None:
        self.leave_room(sid, "engines", namespace="/gaia")
        async with self.session(sid) as session:
            session.clear()
        async with db.scoped_session() as session:
            engine = await Engine.get(session, engine_id=sid)
            if engine is None:
                return
            await self.ouranos_dispatcher.emit(
                "ecosystem_status",
                {ecosystem.uid: {"status": ecosystem.status, "connected": False}
                 for ecosystem in engine.ecosystems},
                namespace="application"
            )
            self.logger.info(f"Engine {engine.uid} disconnected")

    async def on_register_engine(self, sid, data: SocketIOEnginePayloadDict) -> None:
        data: SocketIOEnginePayloadDict = self.validate_payload(
            data, SocketIOEnginePayload, dict)
        validated = False
        remote_addr: str
        if self.broker_type == "socketio":
            engine_uid = data.get("engine_uid")
            self.logger.debug(
                f"Received 'register_engine' from engine {engine_uid}")
            async with self.session(sid) as session:
                remote_addr = session["REMOTE_ADDR"]
            if engine_uid:
                validated = True
            else:
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
            await sleep(3)
            if self.broker_type == "socketio":
                await self.emit("registration_ack", room=sid)
            elif self.broker_type == "dispatcher":
                await self.emit("registration_ack", room=sid)
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
            ecosystems = await Ecosystem.get_multiple(session, data)
            for ecosystem in ecosystems:
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
        data: list[BaseInfoConfigPayloadDict] = self.validate_payload(
            data, BaseInfoConfigPayload, list)
        engines_in_config: list[str] = []
        ecosystems_status: list[dict[str, str]] = []
        ecosystems_to_log: list[str] = []
        async with db.scoped_session() as session:
            for payload in data:
                ecosystem = payload["data"]
                engines_in_config.append(ecosystem["uid"])
                ecosystems_status.append({"uid": payload["uid"], "status": ecosystem["status"]})
                ecosystems_to_log.append(ecosystem["name"])
                await Ecosystem.update_or_create(
                    session, {
                        **ecosystem,
                        "in_config":True,
                        "last_seen": datetime.now(timezone.utc)
                    }
                )

            # Remove ecosystems not in `ecosystems.cfg` anymore
            stmt = (
                select(Ecosystem)
                .where(Ecosystem.engine_uid == engine_uid)
                .where(Ecosystem.uid.not_in(engines_in_config))
            )
            result = await session.execute(stmt)
            not_used = result.scalars().all()
            for ecosystem in not_used:
                ecosystem.in_config = False

        self.logger.debug(
            f"Logged base info from ecosystem(s): {humanize_list(ecosystems_to_log)}"
        )
        await self.ouranos_dispatcher.emit(
            "ecosystem_status",
            data=ecosystems_status,
            namespace="application"
        )

    @registration_required
    async def on_environmental_parameters(
            self,
            sid: str,
            data: list[EnvironmentConfigPayloadDict],
            engine_uid: str
    ) -> None:
        self.logger.debug(
            f"Received 'environmental_parameters' from engine: {engine_uid}")
        data: list[EnvironmentConfigPayloadDict] = self.validate_payload(
            data, EnvironmentConfigPayload, list)
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
                await Lighting.update_or_create(
                    session, {"method": sky["lighting"]}, uid)
                environment_parameters_in_config: list[str] = []
                for param in ecosystem["climate"]:
                    environment_parameters_in_config.append(param["parameter"])
                    await EnvironmentParameter.update_or_create(
                        session, param, uid)

                # Remove environmental parameters not used anymore
                stmt = (
                    delete(EnvironmentParameter)
                    .where(EnvironmentParameter.ecosystem_uid == uid)
                    .where(EnvironmentParameter.parameter.not_in(environment_parameters_in_config))
                )
                await session.execute(stmt)

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
        data: list[HardwareConfigPayloadDict] = self.validate_payload(
            data, HardwareConfigPayload, list)
        ecosystems_to_log: list[str] = []
        async with db.scoped_session() as session:
            for payload in data:
                hardware_in_config = []
                uid = payload["uid"]
                ecosystems_to_log.append(
                    await get_ecosystem_name(uid, session=session)
                )
                for hardware in payload["data"]:
                    hardware_uid = hardware.pop("uid")
                    hardware_in_config.append(hardware_uid)
                    hardware["ecosystem_uid"] = uid
                    # TODO: register multiplexer ?
                    del hardware["multiplexer_model"]
                    measures_to_add = []
                    for measure in hardware["measures"]:
                        if not bool(await Measure.get(session, measure)):
                            measures_to_add.append(
                                {"name": measure, "unit": ""}
                            )
                    if measures_to_add:
                        await Measure.create(session, measures_to_add)
                    await Hardware.update_or_create(
                        session, values={**hardware, "in_config": True},
                        uid=hardware_uid)
                    await sleep(0)

                # Remove hardware not in `ecosystems.cfg` anymore
                stmt = (
                    select(Hardware)
                    .where(Hardware.ecosystem_uid == uid)
                    .where(Hardware.uid.not_in(hardware_in_config))
                )
                result = await session.execute(stmt)
                not_used = result.scalars().all()
                for hardware in not_used:
                    hardware.in_config = False
        self.logger.debug(
            f"Logged hardware info from ecosystem(s): {humanize_list(ecosystems_to_log)}"
        )

    # --------------------------------------------------------------------------
    #   Events Gaia -> Aggregator -> Api
    # --------------------------------------------------------------------------
    @registration_required
    @dispatch_to_application
    async def on_management(
            self,
            sid: str,
            data: list[ManagementConfigPayloadDict],
            engine_uid: str
    ) -> None:
        self.logger.debug(f"Received 'management' from engine: {engine_uid}")
        data: list[ManagementConfigPayloadDict] = self.validate_payload(
            data, ManagementConfigPayload, list)
        ecosystems_to_log: list[str] = []
        async with db.scoped_session() as session:
            for payload in data:
                ecosystem = payload["data"]
                uid: str = payload["uid"]
                ecosystems_to_log.append(
                    await get_ecosystem_name(uid, session=session)
                )
                ecosystem_obj = await Ecosystem.get(session, uid)
                ecosystem_obj.reset_managements()
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
    async def on_sensors_data(
            self,
            sid: str,
            data: list[SensorsDataPayloadDict],
            engine_uid: str
    ) -> None:
        self.logger.debug(
            f"Received 'sensors_data' from engine: {engine_uid}"
        )
        data: list[SensorsDataPayloadDict] = self.validate_payload(
            data, SensorsDataPayload, list)
        sensors_data: list[SensorDataRecord] = []
        last_log: dict[str, datetime] = {}
        for ecosystem in data:
            ecosystem_data = ecosystem["data"]
            timestamp = ecosystem_data["timestamp"]
            for raw_record in ecosystem_data["records"]:
                record: gvSensorRecord = gvSensorRecord(*raw_record)
                record_timestamp = record.timestamp if record.timestamp else timestamp
                sensors_data.append(cast(SensorDataRecord, {
                    "ecosystem_uid": ecosystem["uid"],
                    "sensor_uid": record.sensor_uid,
                    "measure": record.measure,
                    "timestamp": record_timestamp,
                    "value": float(record.value),
                }))
                last_log[record.sensor_uid] = record_timestamp
                await sleep(0)
        if not sensors_data:
            return
        logging_period = current_app.config["SENSOR_LOGGING_PERIOD"]

        data: list[SensorsDataPayloadDict] = [
            ecosystem for ecosystem in data
            if (
                logging_period and
                ecosystem["data"]["timestamp"].minute % logging_period == 0
            )
        ]
        # Dispatch current data
        await self.ouranos_dispatcher.emit(
            "current_sensors_data", data=sensors_data, namespace="application",
            ttl=15)
        self.logger.debug(
            f"Sent `current_sensors_data` to Ouranos")
        # Log current data in memory
        async with db.scoped_session() as session:
            await SensorDbCache.insert_data(session, sensors_data)
            hardware_uids = [*{s["sensor_uid"] for s in sensors_data}]
            try:
                await session.commit()
            except IntegrityError:  # Received same data twice if connection issue for ex.
                pass
            else:
                self.logger.info(
                    f"Updated `sensors_data` cache with data from sensors "
                    f"{humanize_list(hardware_uids)}")

        # Filter data that needs to be logged into db
        sensors_data: list[SensorDataRecord] = [
            sensor_data for sensor_data in sensors_data
            if sensor_data["timestamp"].minute % logging_period == 0
        ]
        if not sensors_data:
            return
        # Dispatch the data that will become historic data
        await self.ouranos_dispatcher.emit(
            "historic_sensors_data_update", data=data, namespace="application",
            ttl=15)
        self.logger.debug(
            f"Sent `historic_sensors_data_update` to Ouranos")
        # Log historic data in db
        async with db.scoped_session() as session:
            await SensorRecord.create_records(session, sensors_data)
            # Update the last_log column for hardware
            hardware_uids = [*{s["sensor_uid"] for s in sensors_data}]
            for hardware in await Hardware.get_multiple(session, hardware_uids):
                hardware.last_log = last_log.get(hardware.uid)
            try:
                await session.commit()
            except IntegrityError:  # Received same data twice if connection issue for ex.
                pass
            else:
                # Get ecosystem IDs
                ecosystems = await Ecosystem.get_multiple(
                    session, [payload["uid"] for payload in data])
                self.logger.info(
                    f"Logged sensors data from ecosystem(s) "
                    f"{humanize_list([e.name for e in ecosystems])}")

    @registration_required
    @dispatch_to_application
    async def on_actuator_data(
            self,
            sid: str,
            data: list[ActuatorsDataPayloadDict],
            engine_uid: str
    ) -> None:
        self.logger.debug(
            f"Received 'update_health_data' from {engine_uid}")
        data: list[ActuatorsDataPayloadDict] = self.validate_payload(
            data, ActuatorsDataPayload, list)
        logged: list[str] = []
        async with db.scoped_session() as session:
            for payload in data:
                ecosystem = payload["data"]
                logged.append(
                    await get_ecosystem_name(payload["uid"], session=None)
                )
                for actuator, values in ecosystem.items():
                    await session.merge(ActuatorStatus(
                        ecosystem_uid=payload["uid"],
                        actuator_type=actuator,
                        active=values["active"],
                        mode=values["mode"],
                        status=values["status"],

                    ))
        if logged:
            self.logger.debug(
                f"Logged actuator data from ecosystem(s): "
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
            f"Received 'update_health_data' from {engine_uid}")
        data: list[HealthDataPayloadDict] = self.validate_payload(
            data, HealthDataPayload, list)
        logged: list[str] = []
        values: list[dict] = []
        for payload in data:
            raw_ecosystem = payload["data"]
            ecosystem = gvHealthRecord(*raw_ecosystem)
            logged.append(
                await get_ecosystem_name(payload["uid"], session=None)
            )
            health_data = {
                "ecosystem_uid": payload["uid"],
                "timestamp": ecosystem.timestamp,
                "green": ecosystem.green,
                "necrosis": ecosystem.necrosis,
                "health_index": ecosystem.index
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
        data: list[LightDataPayloadDict] = self.validate_payload(
            data, LightDataPayload, list)
        ecosystems_to_log: list[str] = []
        async with db.scoped_session() as session:
            for payload in data:
                ecosystems_to_log.append(
                    await get_ecosystem_name(payload["uid"], session)
                )
                ecosystem = payload["data"]
                light_info = {
                    "ecosystem_uid": payload["uid"],
                    "method": ecosystem["method"],
                    "morning_start": ecosystem["morning_start"],
                    "morning_end": ecosystem["morning_end"],
                    "evening_start": ecosystem["evening_start"],
                    "evening_end": ecosystem["evening_end"]
                }
                await Lighting.update_or_create(session, light_info)
        self.logger.debug(
            f"Logged light data from ecosystem(s): {humanize_list(ecosystems_to_log)}"
        )

    # ---------------------------------------------------------------------------
    #   Events Api -> Aggregator -> Gaia
    # ---------------------------------------------------------------------------
    async def _turn_actuator(self, sid, data: TurnActuatorPayloadDict) -> None:
        data: TurnActuatorPayloadDict = self.validate_payload(
            data, TurnActuatorPayload, dict)
        async with db.scoped_session() as session:
            ecosystem_uid = data["ecosystem_uid"]
            ecosystem = await Ecosystem.get(session, ecosystem_uid)
            try:
                engine_sid = ecosystem.engine.sid
            except (AttributeError, Exception):
                engine_sid = None
        if self.broker_type == "socketio":
            await self.emit(
                "turn_actuator", data=data, namespace="/gaia", room=engine_sid)
        elif self.broker_type == "dispatcher":
            await self.emit(
                "turn_actuator", data=data, namespace="/gaia", room=engine_sid,
                ttl=30)
        else:
            raise TypeError("Event broker_type is invalid")

    async def turn_light(self, sid, data) -> None:
        if data.get("actuator"):
            data["actuator"] = "light"
        await self._turn_actuator(sid, data)

    async def turn_actuator(self, sid, data) -> None:
        await self._turn_actuator(sid, data)

    async def crud(self, sid, data: CrudPayloadDict) -> None:
        engine_uid = data["routing"]["engine_uid"]
        self.logger.debug(
            f"""Sending crud request {data['uuid']} ({data["action"]} 
            {data["target"]}) to engine '{engine_uid}'."""
        )
        async with db.scoped_session() as session:
            engine_sid = await get_engine_sid(engine_uid)
            await CrudRequest.create(session, {
                "uuid": UUID(data["uuid"]),
                "engine_uid": engine_uid,
                "ecosystem_uid": data["routing"]["ecosystem_uid"],
                "action": data["action"],
                "target": data["target"],
                "payload": json.dumps(data["data"]),
            })
        if self.broker_type == "socketio":
            await self.emit(
                "crud", data=data, namespace="/gaia", room=engine_sid)
        elif self.broker_type == "dispatcher":
            await self.emit(
                "crud", data=data, namespace="/gaia", room=engine_sid, ttl=30)
        else:
            raise TypeError("Event broker_type is invalid")

    # Response to crud, actual path: Gaia -> Aggregator
    async def on_crud_result(self, sid, data: CrudResultDict):
        self.logger.debug(f"Received crud result for request {data['uuid']}")
        async with db.scoped_session() as session:
            crud_request = await CrudRequest.get(session, UUID(data["uuid"]))
            crud_request.result = data["status"]
            crud_request.message = data["message"]


class DispatcherBasedGaiaEvents(AsyncEventHandler, Events):
    broker_type = "dispatcher"

    def __init__(self) -> None:
        super().__init__(namespace="/gaia")


class SioBasedGaiaEvents(AsyncNamespace, Events):
    broker_type = "socketio"

    def __init__(self) -> None:
        super().__init__(namespace="/gaia")
