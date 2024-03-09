from __future__ import annotations

from asyncio import sleep
from datetime import datetime, timezone
import inspect
import logging
from typing import cast, overload, Type, TypedDict
from uuid import UUID

from cachetools import LRUCache
from pydantic import TypeAdapter, ValidationError
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from dispatcher import AsyncDispatcher, AsyncEventHandler
import gaia_validators as gv

from ouranos import current_app, db, json
from ouranos.aggregator.decorators import (
    dispatch_to_application, registration_required)
from ouranos.core.database.models.gaia import (
    ActuatorStatus, CrudRequest, Ecosystem, Engine, EnvironmentParameter,
    Hardware, HealthRecord, Lighting, Measure, Place, SensorRecord)
from ouranos.core.database.models.memory import SensorDbCache
from ouranos.core.utils import humanize_list


_ecosystem_name_cache = LRUCache(maxsize=32)
_ecosystem_sid_cache = LRUCache(maxsize=32)


class SensorDataRecord(TypedDict):
    ecosystem_uid: str
    sensor_uid: str
    measure: str
    value: float
    timestamp: datetime


# ------------------------------------------------------------------------------
#   Utility functions
# ------------------------------------------------------------------------------
async def get_ecosystem_name(
        ecosystem_uid: str,
        session: AsyncSession | None = None
) -> str:
    try:
        return _ecosystem_name_cache[ecosystem_uid]
    except KeyError:
        async def inner_func(session: AsyncSession, ecosystem_uid: str) -> str:
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
        async def inner_func(session: AsyncSession, engine_uid: str) -> str:
            engine_obj = await Engine.get(session, engine_uid)
            if engine_obj is not None:
                sid = engine_obj.sid
                _ecosystem_sid_cache[engine_uid] = sid
                return sid

        if session is not None:
            return await inner_func(session, engine_uid)
        async with db.scoped_session() as session:
            return await inner_func(session, engine_uid)


# ------------------------------------------------------------------------------
#   BaseEvents class with common validation method
# ------------------------------------------------------------------------------
class BaseEvents(AsyncEventHandler):
    def __init__(self, *args, **kwargs) -> None:
        kwargs["namespace"] = "/gaia"
        super().__init__(*args, **kwargs)
        self.logger: logging.Logger = logging.getLogger("ouranos.aggregator")

    @overload
    def validate_payload(
            self,
            data: dict,
            model_cls: Type[gv.BaseModel],
            type_=dict
    ) -> dict:
        ...

    @overload
    def validate_payload(
            self,
            data: list[dict],
            model_cls: Type[gv.BaseModel],
            type_=list[dict]
    ) -> list[dict]:
        ...

    def validate_payload(
            self,
            data: dict | list[dict],
            model_cls: Type[gv.BaseModel],
            type_: Type,
    ) -> dict | list[dict]:
        if not data:
            event = inspect.stack()[1].function.lstrip("on_")
            self.logger.error(
                f"Encountered an error while validating '{event}' data. Error "
                f"msg: Empty data."
            )
            raise ValidationError("Empty data")
        if not isinstance(data, type_):
            event = inspect.stack()[1].function.lstrip("on_")
            received = type(data)
            self.logger.error(
                f"Encountered an error while validating '{event}' data. Error "
                f"msg: Wrong data format, expected '{type_}', received "
                f"'{received}'."
            )
            raise ValidationError(f"Data is not of the expected type '{type_}'")
        try:
            if isinstance(data, list):
                temp: list[gv.BaseModel] = TypeAdapter(list[model_cls]).validate_python(data)
                return [obj.model_dump() for obj in temp]
            elif isinstance(data, dict):
                return model_cls(**data).model_dump()
        except ValidationError as e:
            event = inspect.stack()[1].function.lstrip("on_")
            msg_list = [f"{error['loc'][0]}: {error['msg']}" for error in e.errors()]
            self.logger.error(
                f"Encountered an error while validating '{event}' data. Error "
                f"msg: {', '.join(msg_list)}"
            )
            raise


# ------------------------------------------------------------------------------
#   Events class handling all events except short-lived payloads (stream)
# ------------------------------------------------------------------------------
class GaiaEvents(BaseEvents):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.logger = logging.getLogger("ouranos.aggregator")
        self._ouranos_dispatcher: AsyncDispatcher | None = None

    @property
    def ouranos_dispatcher(self) -> AsyncDispatcher:
        if not self._ouranos_dispatcher:
            raise RuntimeError("You need to set dispatcher")
        return self._ouranos_dispatcher

    @ouranos_dispatcher.setter
    def ouranos_dispatcher(
            self,
            dispatcher: AsyncDispatcher
    ) -> None:
        self._ouranos_dispatcher = dispatcher
        self.ouranos_dispatcher.on("turn_light", self.turn_light)
        self.ouranos_dispatcher.on("turn_actuator", self.turn_actuator)
        self.ouranos_dispatcher.on("crud", self.crud)

    # ---------------------------------------------------------------------------
    #   Events Gaia <-> Aggregator
    # ---------------------------------------------------------------------------
    async def on_connect(
            self,
            sid: UUID,
            environ: dict,
    ) -> None:
        self.logger.info(f"Connected to the message broker.")
        await self.emit("register", ttl=5)
        self.logger.info(f"Requesting connected 'Gaia' instances to register.")

    async def on_disconnect(
            self,
            sid: UUID,
            *args,  # noqa
    ) -> None:
        self.leave_room("engines")
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
                namespace="application-internal"
            )
            self.logger.info(f"Engine {engine.uid} disconnected")

    async def on_register_engine(
            self,
            sid: UUID,
            data: gv.EnginePayloadDict,
    ) -> None:
        data: gv.EnginePayloadDict = self.validate_payload(
            data, gv.EnginePayload, dict)
        engine_uid: str = data["engine_uid"]
        remote_addr: str = data["address"]
        self.logger.info(
            f"Received registration request from engine {engine_uid} with sid {sid}")
        async with self.session(sid) as session:
            session["engine_uid"] = engine_uid
            session["init_data"] = {
                "base_info", "environmental_parameters", "hardware",
                "management", "actuator_data", "light_data",
            }
        now = datetime.now(timezone.utc).replace(microsecond=0)
        engine_info = {
            "uid": engine_uid,
            "sid": sid,
            "last_seen": now,
            "address": f"{remote_addr}",
        }
        async with db.scoped_session() as session:
            await Engine.update_or_create(session, engine_info)
        self.enter_room(room="engines")

        # await sleep(3)  # Allow slower Raspi0 to finish Gaia startup
        self.logger.info(f"Successful registration of engine {engine_uid} with sid {sid}")
        await self.emit("registration_ack", data=sid, ttl=15, to=sid)

    @registration_required
    async def on_initialized(
            self,
            sid: UUID,  # noqa
            engine_uid: str,
    ) -> None:
        async with self.session(sid) as session:
            missing = session["init_data"]
        if not missing:
            self.logger.info(
                f"Successfully received initialization data from engine {engine_uid}.")
            await self.emit("initialized_ack", data=None)
        else:
            self.logger.warning(
                f"Missing initialization data from engine {engine_uid}: {missing}.")
            await self.emit("initialized_ack", data=[*missing])

    @registration_required
    async def on_ping(
            self,
            sid: UUID,
            data: list[dict[str, str]],
            engine_uid: str,
    ) -> None:
        self.logger.debug(f"Received 'ping' from engine {engine_uid}")
        await self.emit("pong", to=sid)
        now = datetime.now(timezone.utc).replace(microsecond=0)
        ecosystems_seen: list[str] = []
        await self.ouranos_dispatcher.emit(
            "ecosystems_heartbeat",
            data={
                "engine_uid": engine_uid,
                "ecosystems": data,
            },
            namespace="application-internal"
        )
        async with db.scoped_session() as session:
            engine = await Engine.get(session, sid)
            if engine:
                engine.last_seen = now
            ecosystems = await Ecosystem.get_multiple(
                session, [ecosystem["uid"] for ecosystem in data])
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
            sid: UUID,  # noqa
            data: list[gv.BaseInfoConfigPayloadDict],
            engine_uid: str
    ) -> None:
        self.logger.debug(f"Received 'base_info' from engine: {engine_uid}")
        async with self.session(sid) as session:
            session["init_data"].discard("base_info")
        data: list[gv.BaseInfoConfigPayloadDict] = self.validate_payload(
            data, gv.BaseInfoConfigPayload, list)
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
            namespace="application-internal"
        )

    @registration_required
    async def on_environmental_parameters(
            self,
            sid: UUID,  # noqa
            data: list[gv.EnvironmentConfigPayloadDict],
            engine_uid: str
    ) -> None:
        self.logger.debug(
            f"Received 'environmental_parameters' from engine: {engine_uid}")
        async with self.session(sid) as session:
            session["init_data"].discard("environmental_parameters")
        data: list[gv.EnvironmentConfigPayloadDict] = self.validate_payload(
            data, gv.EnvironmentConfigPayload, list)
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
            sid: UUID,  # noqa
            data: list[gv.HardwareConfigPayloadDict],
            engine_uid: str
    ) -> None:
        self.logger.debug(f"Received 'hardware' from engine: {engine_uid}")
        async with self.session(sid) as session:
            session["init_data"].discard("hardware")
        data: list[gv.HardwareConfigPayloadDict] = self.validate_payload(
            data, gv.HardwareConfigPayload, list)
        ecosystems_to_log: list[str] = []
        async with db.scoped_session() as session:
            for payload in data:
                hardware_in_config = []
                uid = payload["uid"]
                ecosystems_to_log.append(
                    await get_ecosystem_name(uid, session=session)
                )
                for hardware in payload["data"]:
                    hardware: dict  # Treat hardware as regular dict
                    hardware_uid = hardware.pop("uid")
                    hardware_in_config.append(hardware_uid)
                    hardware["ecosystem_uid"] = uid
                    # TODO: register multiplexer ?
                    del hardware["multiplexer_model"]
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
            sid: UUID,  # noqa
            data: list[gv.ManagementConfigPayloadDict],
            engine_uid: str
    ) -> None:
        self.logger.debug(f"Received 'management' from engine: {engine_uid}")
        async with self.session(sid) as session:
            session["init_data"].discard("management")
        data: list[gv.ManagementConfigPayloadDict] = self.validate_payload(
            data, gv.ManagementConfigPayload, list)
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
                for management in gv.ManagementFlags:
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
            sid: UUID,  # noqa
            data: list[gv.SensorsDataPayloadDict],
            engine_uid: str
    ) -> None:
        self.logger.debug(
            f"Received 'sensors_data' from engine: {engine_uid}")
        data: list[gv.SensorsDataPayloadDict] = self.validate_payload(
            data, gv.SensorsDataPayload, list)
        sensors_data: list[SensorDataRecord] = []
        for ecosystem in data:
            ecosystem_data = ecosystem["data"]
            timestamp = ecosystem_data["timestamp"]
            for raw_record in ecosystem_data["records"]:
                record = gv.SensorRecord(*raw_record)
                record_timestamp = record.timestamp if record.timestamp else timestamp
                sensors_data.append(cast(SensorDataRecord, {
                    "ecosystem_uid": ecosystem["uid"],
                    "sensor_uid": record.sensor_uid,
                    "measure": record.measure,
                    "value": float(record.value),
                    "timestamp": record_timestamp,
                }))
                await sleep(0)
        if not sensors_data:
            return

        # Dispatch current data
        await self.ouranos_dispatcher.emit(
            "current_sensors_data", data=sensors_data,
            namespace="application-internal", ttl=15)
        self.logger.debug(f"Sent `current_sensors_data` to the web API")
        # Log current data in memory DB
        async with db.scoped_session() as session:
            await SensorDbCache.insert_data(session, sensors_data)
            hardware_uids = [*{s["sensor_uid"] for s in sensors_data}]
            try:
                await session.commit()
            except IntegrityError:  # Received same data twice if connection issue for ex.
                pass
            else:
                self.logger.debug(
                    f"Updated `sensors_data` cache with data from sensors "
                    f"{humanize_list(hardware_uids)}")

    async def log_sensors_data(self) -> None:
        logging_period = current_app.config["SENSOR_LOGGING_PERIOD"]
        if logging_period is None:
            return

        last_log: dict[str, datetime] = {}
        hardware_uids: set[str] = set()
        ecosystem_uids: set[str] = set()
        records_to_log: list[SensorDataRecord] = []

        async with db.scoped_session() as session:
            recent_sensors_record = await SensorDbCache.get_recent(
                session, discard_logged=True)
            # Filter data that needs to be logged into db
            for record in recent_sensors_record:
                if record.timestamp.minute % logging_period == 0:
                    last_log[record.sensor_uid] = record.timestamp
                    hardware_uids.add(record.sensor_uid)
                    ecosystem_uids.add(record.ecosystem_uid)
                    records_to_log.append(cast(SensorDataRecord, {
                        "ecosystem_uid": record.ecosystem_uid,
                        "sensor_uid": record.sensor_uid,
                        "measure": record.measure,
                        "value": record.value,
                        "timestamp": record.timestamp,
                    }))
                    record.logged = True

        if not records_to_log:
            return
        # Dispatch the data that will become historic data
        await self.ouranos_dispatcher.emit(
            "historic_sensors_data_update", data=records_to_log,
            namespace="application-internal", ttl=15)
        self.logger.debug(
            f"Sent `historic_sensors_data_update` to the web API")
        # Log historic data in db
        async with db.scoped_session() as session:
            await SensorRecord.create_records(session, records_to_log)
            # Update the last_log column for hardware
            for hardware in await Hardware.get_multiple(session, [*hardware_uids]):
                hardware.last_log = last_log.get(hardware.uid)
            await session.commit()
            # Get ecosystem IDs
            ecosystems = await Ecosystem.get_multiple(
                session, ecosystems=[*ecosystem_uids])
            self.logger.info(
                f"Logged sensors data from ecosystem(s) "
                f"{humanize_list([e.name for e in ecosystems])}")

    @registration_required
    async def on_places_list(
            self,
            sid: UUID,  # noqa
            data: gv.BufferedSensorsDataPayloadDict,
            engine_uid: str
    ) -> None:
        self.logger.debug(
            f"Received 'places_list' from {engine_uid}.")
        payload: gv.PlacesPayloadDict = self.validate_payload(
            data, gv.PlacesPayload, dict)
        async with db.scoped_session() as session:
            for place in payload["data"]:
                coordinates = {
                    "latitude": place["coordinates"][0],
                    "longitude": place["coordinates"][1],
                }
                await Place.update_or_create(
                    session, coordinates, engine_uid, place["name"])
            await session.commit()

    @registration_required
    async def on_buffered_sensors_data(
            self,
            sid: UUID,
            data: gv.BufferedSensorsDataPayloadDict,
            engine_uid: str
    ) -> None:
        self.logger.debug(
            f"Received 'buffered_sensors_data' from {engine_uid}")
        data: gv.BufferedSensorsDataPayloadDict = self.validate_payload(
            data, gv.BufferedSensorsDataPayload, dict)
        async with db.scoped_session() as session:
            uuid: UUID = data["uuid"]
            try:
                records = [
                    cast(SensorDataRecord, {
                        "ecosystem_uid": record[0],
                        "sensor_uid": record[1],
                        "measure": record[2],
                        "value": record[3],
                        "timestamp": record[4],
                    })
                    for record in data["data"]
                ]
                await SensorRecord.create_records(session, records)
            except Exception as e:
                await self.emit(
                    "buffered_data_ack",
                    data=gv.RequestResult(
                        uuid=uuid,
                        status=gv.Result.failure,
                        message=str(e)
                    ).model_dump(),
                    namespace="/gaia",
                    to=sid
                )
            else:
                await self.emit(
                    "buffered_data_ack",
                    data=gv.RequestResult(
                        uuid=uuid,
                        status=gv.Result.success,
                    ).model_dump(),
                    namespace="/gaia",
                    to=sid
                )

    @registration_required
    @dispatch_to_application
    async def on_actuator_data(
            self,
            sid: UUID,  # noqa
            data: list[gv.ActuatorsDataPayloadDict],
            engine_uid: str
    ) -> None:
        self.logger.debug(f"Received 'actuator_data' from {engine_uid}")
        async with self.session(sid) as session:
            session["init_data"].discard("actuator_data")
        data: list[gv.ActuatorsDataPayloadDict] = self.validate_payload(
            data, gv.ActuatorsDataPayload, list)
        logged: list[str] = []
        async with db.scoped_session() as session:
            for payload in data:
                ecosystem = payload["data"]
                logged.append(
                    await get_ecosystem_name(payload["uid"], session=None)
                )
                for actuator, values in ecosystem.items():
                    await session.merge(
                        ActuatorStatus(
                            ecosystem_uid=payload["uid"],
                            actuator_type=actuator,
                            active=values["active"],
                            mode=values["mode"],
                            status=values["status"],
                        )
                    )
        if logged:
            self.logger.debug(
                f"Logged actuator data from ecosystem(s): "
                f"{humanize_list(logged)}"
            )

    @registration_required
    @dispatch_to_application
    async def on_health_data(
            self,
            sid: UUID,  # noqa
            data: list[gv.HealthDataPayloadDict],
            engine_uid: str
    ) -> None:
        self.logger.debug(f"Received 'health_data' from {engine_uid}")
        async with self.session(sid) as session:
            session["init_data"].discard("health_data")
        data: list[gv.HealthDataPayloadDict] = self.validate_payload(
            data, gv.HealthDataPayload, list)
        logged: list[str] = []
        values: list[dict] = []
        for payload in data:
            raw_ecosystem = payload["data"]
            ecosystem = gv.HealthRecord(*raw_ecosystem)
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
            sid: UUID,  # noqa
            data: list[gv.LightDataPayloadDict],
            engine_uid: str
    ) -> None:
        self.logger.debug(f"Received 'light_data' from {engine_uid}")
        async with self.session(sid) as session:
            session["init_data"].discard("light_data")
        data: list[gv.LightDataPayloadDict] = self.validate_payload(
            data, gv.LightDataPayload, list)
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
    async def _turn_actuator(
            self,
            sid: UUID,  # noqa
            data: gv.TurnActuatorPayloadDict
    ) -> None:
        data: gv.TurnActuatorPayloadDict = self.validate_payload(
            data, gv.TurnActuatorPayload, dict)
        async with db.scoped_session() as session:
            ecosystem_uid = data["ecosystem_uid"]
            ecosystem = await Ecosystem.get(session, ecosystem_uid)
            try:
                engine_sid = ecosystem.engine.sid
            except (AttributeError, Exception):
                engine_sid = None
        await self.emit(
            "turn_actuator", data=data, namespace="gaia", to=engine_sid,
            ttl=30)

    async def turn_light(
            self,
            sid: UUID,  # noqa
            data: gv.TurnActuatorPayloadDict,
    ) -> None:
        if data.get("actuator"):
            data["actuator"] = gv.HardwareType.light
        await self._turn_actuator(sid, data)

    async def turn_actuator(
            self,
            sid: UUID,  # noqa
            data: gv.TurnActuatorPayloadDict,
    ) -> None:
        await self._turn_actuator(sid, data)

    async def crud(
            self,
            sid: UUID,  # noqa
            data: gv.CrudPayloadDict,
    ) -> None:
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
        await self.emit(
            "crud", data=data, namespace="/gaia", to=engine_sid, ttl=30)

    # Response to crud event, actual path: Gaia -> Aggregator -> Api
    async def on_crud_result(
            self,
            sid: UUID,  # noqa
            data: gv.RequestResultDict
    ) -> None:
        self.logger.debug(f"Received crud result for request {data['uuid']}")
        async with db.scoped_session() as session:
            crud_request = await CrudRequest.get(session, UUID(data["uuid"]))
            crud_request.result = data["status"]
            crud_request.message = data["message"]


# ------------------------------------------------------------------------------
#   StreamEvents class handling short-lived payloads (stream)
# ------------------------------------------------------------------------------
class StreamGaiaEvents(BaseEvents):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.logger = logging.getLogger("ouranos.aggregator.stream")

    async def on_ecosystem_image(
        self,
        sid: UUID,  # noqa
        data: dict
    ) -> None:
        pass
