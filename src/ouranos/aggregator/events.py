from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock
import inspect
import logging
from typing import cast, Type, TypedDict, TypeVar
from uuid import UUID

from cachetools import LRUCache
from pydantic import TypeAdapter, ValidationError
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from dispatcher import AsyncDispatcher, AsyncEventHandler
import gaia_validators as gv

from ouranos import current_app, db, json
from ouranos.aggregator.decorators import (
    dispatch_to_application, registration_required)
from ouranos.core.database.models.abc import RecordMixin
from ouranos.core.database.models.gaia import (
    ActuatorRecord, ActuatorState, CrudRequest, Ecosystem, Engine,
    EnvironmentParameter, Hardware, HealthRecord, Lighting, Place, SensorAlarm,
    SensorDataRecord, SensorDataCache)
from ouranos.core.utils import humanize_list


PT = TypeVar("PT", dict, list[dict])


_ecosystem_name_cache = LRUCache(maxsize=32)
_ecosystem_sid_cache = LRUCache(maxsize=32)


class SensorDataRecordDict(TypedDict):
    ecosystem_uid: str
    sensor_uid: str
    measure: str
    value: float
    timestamp: datetime


class SensorAlarmDict(TypedDict):
    sensor_uid: str
    measure: str
    position: gv.Position
    delta: float
    level: gv.WarningLevel
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
            ecosystem = await Ecosystem.get(session, uid=ecosystem_uid)
            if ecosystem is not None:
                _ecosystem_name_cache[ecosystem_uid] = ecosystem.name
                return ecosystem.name

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
            engine = await Engine.get(session, uid=engine_uid)
            if engine is not None:
                sid = engine.sid
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

    def validate_payload(
            self,
            data: PT,
            model_cls: Type[gv.BaseModel],
            type_: Type[dict] | Type[list],
    ) -> PT:
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
        self._alarms_data: list[SensorAlarmDict] = []
        self._alarms_data_lock: Lock = Lock()

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

    @property
    def alarms_data(self) -> list[SensorAlarmDict]:
        with self._alarms_data_lock:
            return self._alarms_data

    @alarms_data.setter
    def alarms_data(self, value: list[SensorAlarmDict]) -> None:
        with self._alarms_data_lock:
            self._alarms_data = value

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
            engine = await Engine.get_by_id(session, engine_id=sid)
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
                "management", "actuators_data", "light_data",
            }
        now = datetime.now(timezone.utc).replace(microsecond=0)
        engine_info = {
            "sid": sid,
            "last_seen": now,
            "address": f"{remote_addr}",
        }
        async with db.scoped_session() as session:
            await Engine.update_or_create(session, uid=engine_uid, values=engine_info)
        self.enter_room(room="engines")

        # await sleep(3)  # Allow slower Raspi0 to finish Gaia startup
        self.logger.info(f"Successful registration of engine {engine_uid} with sid {sid}")
        await self.emit("registration_ack", data=sid, ttl=15, to=sid)

    @registration_required
    async def on_initialization_data_sent(
            self,
            sid: UUID,  # noqa
            engine_uid: str,
    ) -> None:
        async with self.session(sid) as session:
            missing = session["init_data"]
        if not missing:
            self.logger.info(
                f"Successfully received initialization data from engine {engine_uid}.")
            await self.emit("initialization_ack", data=None)
        else:
            self.logger.warning(
                f"Missing initialization data from engine {engine_uid}: {missing}.")
            await self.emit("initialization_ack", data=[*missing])

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
            engine = await Engine.get(session, uid=engine_uid)
            if engine:
                await Engine.update(session, uid=engine_uid, values={"last_seen": now})
            ecosystems = await Ecosystem.get_multiple(
                session, uid=[ecosystem["uid"] for ecosystem in data])
            for ecosystem in ecosystems:
                ecosystems_seen.append(ecosystem.name)
                await Ecosystem.update(session, uid=ecosystem.uid, values={"last_seen": now})
        self.logger.debug(
            f"Updated last seen info for ecosystem(s) "
            f"{humanize_list(ecosystems_seen)}"
        )

    @registration_required
    async def on_places_list(
            self,
            sid: UUID,  # noqa
            data: gv.PlacesPayloadDict,
            engine_uid: str
    ) -> None:
        self.logger.debug(
            f"Received 'places_list' from {engine_uid}.")
        payload: gv.PlacesPayloadDict = self.validate_payload(
            data, gv.PlacesPayload, dict)
        async with db.scoped_session() as session:
            for place in payload["data"]:
                await Place.update_or_create(
                    session,
                    engine_uid=engine_uid,
                    name=place["name"],
                    values={
                        "latitude": place["coordinates"][0],
                        "longitude": place["coordinates"][1],
                    }
                )
            await session.commit()

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
        ecosystems_in_config: list[str] = []
        ecosystems_status: list[dict[str, str]] = []
        ecosystems_to_log: list[str] = []
        async with db.scoped_session() as session:
            for payload in data:
                ecosystem = payload["data"]
                ecosystem_uid = ecosystem.pop("uid")  # noqa
                ecosystems_in_config.append(ecosystem_uid)
                ecosystems_status.append({"uid": payload["uid"], "status": ecosystem["status"]})
                ecosystems_to_log.append(ecosystem["name"])
                await Ecosystem.update_or_create(
                    session,
                    uid=ecosystem_uid,
                    values={
                        **ecosystem,
                        "in_config": True,
                        "last_seen": datetime.now(timezone.utc)
                    }
                )

                # Add the possible actuator types if missing
                actuator_types = {i for i in gv.HardwareType.actuator}
                actuator_states = await ActuatorState.get_multiple(
                    session, ecosystem_uid=ecosystem_uid, type=[*actuator_types])
                actuator_types_present = {actuator_state.type for actuator_state in actuator_states}
                actuator_types_missing = actuator_types - actuator_types_present
                if actuator_types_missing:
                    await ActuatorState.create_multiple(
                        session,
                        values=[
                            {
                                "ecosystem_uid": ecosystem_uid,
                                "type": actuator_type,
                            } for actuator_type in actuator_types_missing
                        ],
                    )

            # Remove ecosystems not in `ecosystems.cfg` anymore
            stmt = (
                update(Ecosystem)
                .where(Ecosystem.engine_uid == engine_uid)
                .where(Ecosystem.uid.not_in(ecosystems_in_config))
                .values({"in_config": False})
            )
            await session.execute(stmt)

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
                    await get_ecosystem_name(uid, session=session))
                ecosystem = payload["data"]
                nycthemeral_cycle = ecosystem["nycthemeral_cycle"]
                ecosystem_info = {
                    "day_start": nycthemeral_cycle["day"],
                    "night_start": nycthemeral_cycle["night"],
                }
                await Ecosystem.update_or_create(session, uid=uid, values=ecosystem_info)
                await Lighting.update_or_create(
                    session, ecosystem_uid=uid, values={"method": nycthemeral_cycle["lighting"]})
                environment_parameters_in_config: list[str] = []
                for param in ecosystem["climate"]:
                    environment_parameters_in_config.append(param["parameter"])
                    parameter = param.pop("parameter")  # noqa
                    await EnvironmentParameter.update_or_create(
                        session, ecosystem_uid=uid, parameter=parameter,
                        values=param)

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
                    await get_ecosystem_name(uid, session=session))
                for hardware in payload["data"]:
                    hardware_uid = hardware.pop("uid")  # noqa
                    hardware_in_config.append(hardware_uid)
                    hardware["ecosystem_uid"] = uid  # noqa
                    hardware["in_config"] = True  # noqa
                    # TODO: register multiplexer ?
                    del hardware["multiplexer_model"]  # noqa
                    await Hardware.update_or_create(
                        session, uid=hardware_uid, values=hardware)

                # Remove hardware not in `ecosystems.cfg` anymore
                stmt = (
                    select(Hardware)
                    .where(Hardware.ecosystem_uid == uid)
                    .where(Hardware.uid.not_in(hardware_in_config))
                )
                result = await session.execute(stmt)
                not_used = result.all()
                for hardware_row in not_used:
                    await Hardware.update(session, uid=hardware_row.uid, values={"in_config": False})
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

        class EcosystemUpdateData(TypedDict):
            management: str

        ecosystems_to_update: dict[str, EcosystemUpdateData] = {}
        ecosystems_to_log: list[str] = []

        for payload in data:
            uid: str = payload["uid"]
            ecosystem_management = payload["data"]
            management_value: int = 0
            for management in gv.ManagementFlags:
                try:
                    if ecosystem_management[management.name]:
                        management_value |= management.value
                except KeyError:
                    # Not implemented in gaia yet
                    pass

            ecosystems_to_update[uid] = {
                "management": management_value
            }
            ecosystems_to_log.append(
                await get_ecosystem_name(uid, session=None))

        if ecosystems_to_update:
            async with db.scoped_session() as session:
                for ecosystem_uid, update_value in ecosystems_to_update.items():
                    await Ecosystem.update(session, uid=ecosystem_uid, values=update_value)
            self.logger.debug(
                f"Logged management info from ecosystem(s): "
                f"{humanize_list(ecosystems_to_log)}")

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
        sensors_data: list[SensorDataRecordDict] = []
        alarms_data: list[SensorAlarmDict] = []
        for ecosystem in data:
            ecosystem_data = ecosystem["data"]
            timestamp = ecosystem_data["timestamp"]
            for raw_record in ecosystem_data["records"]:
                record = gv.SensorRecord(*raw_record)
                record_timestamp = record.timestamp if record.timestamp else timestamp
                sensors_data.append(cast(SensorDataRecordDict, {
                    "ecosystem_uid": ecosystem["uid"],
                    "sensor_uid": record.sensor_uid,
                    "measure": record.measure,
                    "value": float(record.value),
                    "timestamp": record_timestamp,
                }))
            for raw_alarm in ecosystem_data["alarms"]:
                alarm = gv.SensorAlarm(*raw_alarm)
                alarms_data.append(cast(SensorAlarmDict, {
                    "ecosystem_uid": ecosystem["uid"],
                    "sensor_uid": alarm.sensor_uid,
                    "measure": alarm.measure,
                    "position": alarm.position,
                    "delta": alarm.delta,
                    "level": alarm.level,
                    "timestamp": timestamp,
                }))
        if not sensors_data:
            return

        # Dispatch current data
        await self.ouranos_dispatcher.emit(
            "current_sensors_data", data=sensors_data,
            namespace="application-internal", ttl=15)
        self.logger.debug(f"Sent `current_sensors_data` to the web API")
        # Log current data in memory DB
        async with db.scoped_session() as session:
            await SensorDataCache.insert_data(session, sensors_data)
            hardware_uids = [*{s["sensor_uid"] for s in sensors_data}]
            try:
                await session.commit()
            except IntegrityError:  # Received same data twice if connection issue for ex.
                pass
            else:
                self.logger.debug(
                    f"Updated `sensors_data` cache with data from sensors "
                    f"{humanize_list(hardware_uids)}")
        # Memorise alarms
        self.alarms_data = alarms_data

    async def log_sensors_data(self) -> None:
        logging_period = current_app.config["SENSOR_LOGGING_PERIOD"]
        if logging_period is None:
            return

        class HardwareUpdateData(TypedDict):
            last_log: datetime

        records_to_create: list[SensorDataRecordDict] = []
        hardware_to_update: dict[str, HardwareUpdateData] = {}
        ecosystems_to_log: set[str] = set()

        async with db.scoped_session() as session:
            recent_sensors_record = await SensorDataCache.get_recent(
                session, discard_logged=True)
            # Filter data that needs to be logged into db
            for record in recent_sensors_record:
                if record.timestamp.minute % logging_period == 0:
                    hardware_to_update[record.sensor_uid] = {
                        "last_log": record.timestamp,
                    }
                    ecosystems_to_log.add(
                        await get_ecosystem_name(record.ecosystem_uid, session=session))
                    records_to_create.append(cast(SensorDataRecordDict, {
                        "ecosystem_uid": record.ecosystem_uid,
                        "sensor_uid": record.sensor_uid,
                        "measure": record.measure,
                        "value": record.value,
                        "timestamp": record.timestamp,
                    }))
                    record.logged = True

            alarms = self.alarms_data  # Use the lock a single time
            alarms_to_log: list[SensorAlarmDict] = [
                alarm for alarm in alarms
                if alarm["timestamp"].minute % logging_period == 0
            ]

        if not records_to_create:
            return
        # Dispatch the data that will become historic data
        await self.ouranos_dispatcher.emit(
            "historic_sensors_data_update", data=records_to_create,
            namespace="application-internal", ttl=15)
        self.logger.debug(
            f"Sent `historic_sensors_data_update` to the web API")
        # Log historic data in db
        async with db.scoped_session() as session:
            await SensorDataRecord.create_records(session, records_to_create)
            # Update the last_log column for hardware
            for hardware_uid, update_value in hardware_to_update.items():
                await Hardware.update(session, uid=hardware_uid, values=update_value)
                ecosystems_to_log.add(
                    await get_ecosystem_name(record.ecosystem_uid, session=session))
            # Log new alarms or lengthen old ones
            for alarm in alarms_to_log:
                await SensorAlarm.create_or_lengthen(session, alarm)
            # Get ecosystem IDs
            self.logger.info(
                f"Logged sensors data from ecosystem(s) "
                f"{humanize_list([*ecosystems_to_log])}")

    async def _handle_buffered_records(
            self,
            record_model: Type[RecordMixin],
            records: list[dict],
            exchange_uuid: UUID,
            sender_sid: UUID,
    ) -> None:
        async with db.scoped_session() as session:
            try:
                await record_model.create_records(session, records)
            except Exception as e:
                await self.emit(
                    "buffered_data_ack",
                    data=gv.RequestResult(
                        uuid=exchange_uuid,
                        status=gv.Result.failure,
                        message=str(e)
                    ).model_dump(),
                    namespace="/gaia",
                    to=sender_sid
                )
            else:
                await self.emit(
                    "buffered_data_ack",
                    data=gv.RequestResult(
                        uuid=exchange_uuid,
                        status=gv.Result.success,
                    ).model_dump(),
                    namespace="/gaia",
                    to=sender_sid
                )

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
        exchange_uuid: UUID = data["uuid"]
        records = [
            {
                "ecosystem_uid": record[0],
                "sensor_uid": record[1],
                "measure": record[2],
                "value": record[3],
                "timestamp": record[4],
            }
            for record in data["data"]
        ]
        await self._handle_buffered_records(
            record_model=SensorDataRecord,
            records=records,
            exchange_uuid=exchange_uuid,
            sender_sid=sid
        )

    @registration_required
    async def on_actuators_data(
            self,
            sid: UUID,  # noqa
            data: list[gv.ActuatorsDataPayloadDict],
            engine_uid: str
    ) -> None:
        self.logger.debug(f"Received 'actuators_data' from {engine_uid}")
        async with self.session(sid) as session:
            session["init_data"].discard("actuators_data")
        data: list[gv.ActuatorsDataPayloadDict] = self.validate_payload(
            data, gv.ActuatorsDataPayload, list)

        class AwareActuatorStateDict(gv.ActuatorStateDict):
            ecosystem_uid: str
            type: gv.HardwareType

        class AwareActuatorStateRecordDict(AwareActuatorStateDict):
            timestamp: datetime | None

        logged: list[str] = []
        data_to_dispatch: list[AwareActuatorStateDict] = []
        records_to_log: list[AwareActuatorStateRecordDict] = []
        async with db.scoped_session() as session:
            for payload in data:
                records = payload["data"]
                logged.append(
                    await get_ecosystem_name(payload["uid"], session=session))
                for record in records:
                    record: gv.ActuatorStateRecord
                    ecosystem_uid=payload["uid"]
                    type_=record[0].name
                    common_data: gv.ActuatorStateDict = {
                        "active": record[1],
                        "mode": record[2],
                        "status": record[3],
                        "level": record[4],
                    }
                    await ActuatorState.update_or_create(
                        session,
                        ecosystem_uid=ecosystem_uid,
                        type=type_,
                        values=common_data
                    )
                    data_to_dispatch.append(cast(AwareActuatorStateDict, {
                        "ecosystem_uid": ecosystem_uid,
                        "type": type_,
                        **common_data
                    }))
                    timestamp = record[5]
                    if timestamp is not None:
                        records_to_log.append(cast(AwareActuatorStateRecordDict, {
                            "ecosystem_uid": ecosystem_uid,
                            "type": type_,
                            "timestamp": timestamp,
                            **common_data,
                        }))
            if records_to_log:
                await ActuatorRecord.create_records(session, records_to_log)
            if data_to_dispatch:
                await self.ouranos_dispatcher.emit(
                    "actuators_data", data=data_to_dispatch,
                    namespace="application-internal", ttl=15)

        if logged:
            self.logger.debug(
                f"Logged actuator data from ecosystem(s): "
                f"{humanize_list(logged)}"
            )

    @registration_required
    async def on_buffered_actuators_data(
            self,
            sid: UUID,
            data: gv.BufferedActuatorsStatePayloadDict,
            engine_uid: str
    ) -> None:
        self.logger.debug(
            f"Received 'buffered_actuators_data' from {engine_uid}")
        data: gv.BufferedActuatorsStatePayloadDict = self.validate_payload(
            data, gv.BufferedActuatorsStatePayload, dict)
        exchange_uuid: UUID = data["uuid"]
        records = [
            {
                "ecosystem_uid": record[0],
                "type": record[1],
                "active": record[2],
                "mode": record[3],
                "status": record[4],
                "level": record[5],
                "timestamp": record[6],
            }
            for record in data["data"]
        ]
        await self._handle_buffered_records(
            record_model=ActuatorRecord,
            records=records,
            exchange_uuid=exchange_uuid,
            sender_sid=sid
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
                await get_ecosystem_name(payload["uid"], session=None))
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
                    await get_ecosystem_name(payload["uid"], session=session))
                ecosystem = payload["data"]
                light_info = {
                    "method": ecosystem["method"],
                    "morning_start": ecosystem["morning_start"],
                    "morning_end": ecosystem["morning_end"],
                    "evening_start": ecosystem["evening_start"],
                    "evening_end": ecosystem["evening_end"]
                }
                await Lighting.update_or_create(
                    session, ecosystem_uid=payload["uid"], values=light_info)
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
            ecosystem = await Ecosystem.get(session, uid=ecosystem_uid)
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
            await CrudRequest.create(
                session,
                uuid=UUID(data["uuid"]),
                values={
                    "engine_uid": engine_uid,
                    "ecosystem_uid": data["routing"]["ecosystem_uid"],
                    "action": data["action"],
                    "target": data["target"],
                    "payload": json.dumps(data["data"])
                }
            )
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
            crud_request = await CrudRequest.get(session, uuid=UUID(data["uuid"]))
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
