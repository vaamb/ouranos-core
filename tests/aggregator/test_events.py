from __future__ import annotations

from asyncio import sleep
from copy import copy
from datetime import datetime,timedelta, timezone

import pytest
from sqlalchemy import select

from gaia_validators import ManagementFlags, TurnActuatorPayload
from sqlalchemy_wrapper import AsyncSQLAlchemyWrapper

from ouranos.aggregator.events import (
    BrokerType, DispatcherBasedGaiaEvents, SocketIOEnginePayload)
from ouranos.core.database.models.gaia import (
    ActuatorStatus, ActuatorType, Ecosystem, Engine, EnvironmentParameter,
    Hardware, HealthRecord, Lighting, SensorRecord)
from ouranos.core.database.models.memory import SensorDbCache
from ouranos.core.exceptions import NotRegisteredError
from ouranos.core.utils import create_time_window

from ..data.gaia import *
from ..utils import MockAsyncDispatcher


def test_handler(
        mock_dispatcher: MockAsyncDispatcher,
        events_handler: DispatcherBasedGaiaEvents
):
    assert events_handler._dispatcher == mock_dispatcher
    assert events_handler.broker_type == BrokerType.dispatcher
    assert events_handler.namespace == "gaia"
    assert len(mock_dispatcher.emit_store) == 0


@pytest.mark.asyncio
async def test_registration_wrapper(
        mock_dispatcher: MockAsyncDispatcher,
        events_handler: DispatcherBasedGaiaEvents
):
    await events_handler.on_ping(engine_sid, [ecosystem_uid])

    # Remove sid from session dict
    mock_dispatcher._sessions[engine_sid] = {}
    with pytest.raises(NotRegisteredError):
        await events_handler.on_ping(engine_sid, [ecosystem_uid])


@pytest.mark.asyncio
async def test_on_connect(
        mock_dispatcher: MockAsyncDispatcher,
        events_handler: DispatcherBasedGaiaEvents
):
    await events_handler.on_connect(engine_sid, "")
    emitted = mock_dispatcher.emit_store[0]
    assert emitted["event"] == "register"
    assert emitted["data"] is None


@pytest.mark.asyncio
async def test_on_disconnect(
        mock_dispatcher: MockAsyncDispatcher,
        events_handler: DispatcherBasedGaiaEvents,
        engine_aware_db: AsyncSQLAlchemyWrapper  # noqa
):
    await events_handler.on_disconnect(engine_sid)

    assert mock_dispatcher._sessions[engine_sid] == {}

    emitted = mock_dispatcher.emit_store[0]
    assert emitted["event"] == "ecosystem_status"
    assert emitted["data"] == {}
    assert emitted["namespace"] == "application"


@pytest.mark.asyncio
async def test_on_register_engine(
        mock_dispatcher: MockAsyncDispatcher,
        events_handler: DispatcherBasedGaiaEvents,
        naive_db: AsyncSQLAlchemyWrapper,
):
    payload = SocketIOEnginePayload(
        engine_uid=engine_uid,
        address=ip_address
    ).model_dump()
    await events_handler.on_register_engine(engine_sid, payload)
    emitted = mock_dispatcher.emit_store[0]
    assert emitted["event"] == "registration_ack"
    assert emitted["namespace"] == "gaia"
    assert emitted["room"] == engine_sid
    assert mock_dispatcher._sessions[engine_sid]["engine_uid"] == engine_uid

    async with naive_db.scoped_session() as session:
        engine = await Engine.get(session, engine_id=engine_uid)
        assert engine.uid == engine_uid
        assert engine.address == ip_address

    wrong_payload = {}
    with pytest.raises(Exception):
        await events_handler.on_register_engine(engine_sid, wrong_payload)


@pytest.mark.asyncio
async def test_on_ping(
        mock_dispatcher: MockAsyncDispatcher,
        events_handler: DispatcherBasedGaiaEvents,
        engine_aware_db: AsyncSQLAlchemyWrapper,
):
    async with engine_aware_db.scoped_session() as session:
        engine = await Engine.get(session, engine_id=engine_uid)
        start = copy(engine.last_seen)
    await sleep(1.1)

    await events_handler.on_ping(engine_sid, [ecosystem_uid])

    async with engine_aware_db.scoped_session() as session:
        engine = await Engine.get(session, engine_id=engine_uid)
        assert engine.last_seen > start


@pytest.mark.asyncio
async def test_on_base_info(
        mock_dispatcher: MockAsyncDispatcher,
        events_handler: DispatcherBasedGaiaEvents,
        naive_db: AsyncSQLAlchemyWrapper,
):
    await events_handler.on_base_info(engine_sid, [base_info_payload])
    emitted = mock_dispatcher.emit_store[0]
    assert emitted["event"] == "ecosystem_status"
    assert emitted["data"] == [
        {"status": base_info["status"], 'uid': base_info["uid"]}
    ]
    assert emitted["namespace"] == "application"

    async with naive_db.scoped_session() as session:
        ecosystem = await Ecosystem.get(session, ecosystem_id=ecosystem_uid)
        assert ecosystem.engine_uid == base_info["engine_uid"]
        assert ecosystem.name == base_info["name"]
        assert ecosystem.status == base_info["status"]

    wrong_payload = {}
    with pytest.raises(Exception):
        await events_handler.on_base_info(engine_sid, [wrong_payload])


@pytest.mark.asyncio
async def test_on_management(
        mock_dispatcher: MockAsyncDispatcher,
        events_handler: DispatcherBasedGaiaEvents,
        ecosystem_aware_db: AsyncSQLAlchemyWrapper,
):
    await events_handler.on_management(engine_sid, [management_payload])

    management_value = 0
    for management in ManagementFlags:
        try:
            if management_data[management.name]:
                management_value += management.value
        except KeyError:
            pass

    async with ecosystem_aware_db.scoped_session() as session:
        ecosystem = await Ecosystem.get(session, ecosystem_id=ecosystem_uid)
        assert ecosystem.management == management_value

    wrong_payload = {}
    with pytest.raises(Exception):
        await events_handler.on_management(engine_sid, [wrong_payload])


@pytest.mark.asyncio
async def test_on_environmental_parameters(
        mock_dispatcher: MockAsyncDispatcher,
        events_handler: DispatcherBasedGaiaEvents,
        ecosystem_aware_db: AsyncSQLAlchemyWrapper,
):
    await events_handler.on_environmental_parameters(engine_sid, [environmental_payload])

    async with ecosystem_aware_db.scoped_session() as session:
        ecosystem = await Ecosystem.get(session, ecosystem_id=ecosystem_uid)
        assert ecosystem.day_start == sky["day"]
        assert ecosystem.night_start == sky["night"]

        light = await Lighting.get(session, ecosystem_uid=ecosystem_uid)
        assert light.method == sky["lighting"]

        environment_parameter = await EnvironmentParameter.get(
            session, uid=ecosystem_uid, parameter=climate["parameter"])
        assert environment_parameter.day == climate["day"]
        assert environment_parameter.night == climate["night"]
        assert environment_parameter.hysteresis == climate["hysteresis"]

    wrong_payload = {}
    with pytest.raises(Exception):
        await events_handler.on_environmental_parameters(engine_sid, [wrong_payload])


@pytest.mark.asyncio
async def test_on_hardware(
        mock_dispatcher: MockAsyncDispatcher,
        events_handler: DispatcherBasedGaiaEvents,
        ecosystem_aware_db: AsyncSQLAlchemyWrapper,
):
    await events_handler.on_hardware(engine_sid, [hardware_payload])

    async with ecosystem_aware_db.scoped_session() as session:
        hardware = await Hardware.get(session, hardware_uid=hardware_data["uid"])
        assert hardware.name == hardware_data["name"]
        assert hardware.level.value == hardware_data["level"]
        assert hardware.address == hardware_data["address"]
        assert hardware.type.value == hardware_data["type"]
        assert hardware.model == hardware_data["model"]
        measures = [measure.name for measure in hardware.measures]
        measures.sort()
        measures_data = copy(hardware_data["measures"])
        measures_data.sort()
        assert measures == measures_data

    wrong_payload = {}
    with pytest.raises(Exception):
        await events_handler.on_hardware(engine_sid, [wrong_payload])


@pytest.mark.asyncio
async def test_on_sensors_data(
        mock_dispatcher: MockAsyncDispatcher,
        events_handler: DispatcherBasedGaiaEvents,
        ecosystem_aware_db: AsyncSQLAlchemyWrapper,
):
    await events_handler.on_sensors_data(engine_sid, [sensors_data_payload])
    emitted = mock_dispatcher.emit_store[0]
    assert emitted["event"] == "current_sensors_data"
    assert emitted["data"] == [{
        'ecosystem_uid': sensors_data_payload["uid"],
        'sensor_uid': sensor_record.sensor_uid,
        'measure': sensor_record.measure,
        'timestamp': sensors_data["timestamp"],
        'value': sensor_record.value
    }]
    assert emitted["namespace"] == "application"

    async with ecosystem_aware_db.scoped_session() as session:
        sensor_data = (await SensorDbCache.get_recent(session))[0]
        assert sensor_data.measure == sensor_record.measure
        assert sensor_data.value == sensor_record.value
        assert sensor_data.timestamp == sensors_data["timestamp"]

    wrong_payload = {}
    with pytest.raises(Exception):
        await events_handler.on_sensors_data(engine_sid, [wrong_payload])


@pytest.mark.asyncio
async def test_on_buffered_sensors_data(
        mock_dispatcher: MockAsyncDispatcher,
        events_handler: DispatcherBasedGaiaEvents,
        ecosystem_aware_db: AsyncSQLAlchemyWrapper,
):
    await events_handler.on_buffered_sensors_data(engine_sid, buffered_data_payload)
    emitted = mock_dispatcher.emit_store[0]
    assert emitted["namespace"] == "gaia"
    assert emitted["room"] == engine_sid
    assert emitted["event"] == "buffered_data_ack"
    result: gv.RequestResultDict = emitted["data"]
    assert result["uuid"] == request_uuid
    assert result["status"] == gv.Result.success

    async with ecosystem_aware_db.scoped_session() as session:
        temperature_data = (
            await SensorRecord.get_records(
                session,
                sensor_uid=hardware_uid,
                measure_name="temperature",
                time_window=create_time_window(
                    end=datetime.now(timezone.utc) + timedelta(days=1))
            )
        )[0]
        assert temperature_data.ecosystem_uid == buffered_data_temperature.ecosystem_uid
        assert temperature_data.sensor_uid == buffered_data_temperature.sensor_uid
        assert temperature_data.measure == buffered_data_temperature.measure
        assert temperature_data.value == buffered_data_temperature.value
        assert temperature_data.timestamp == buffered_data_temperature.timestamp

    """
    # TODO: fix as it currently doesn't fail but yet doesn't save duplicate
    # Resend same data to have an integrity error
    await events_handler.on_buffered_sensors_data(engine_sid, buffered_data_payload)
    emitted = mock_dispatcher.emit_store[0]
    assert emitted["namespace"] == "gaia"
    assert emitted["room"] == engine_sid
    assert emitted["event"] == "buffered_data_ack"
    result: gv.RequestResultDict = emitted["data"]
    assert result["uuid"] == request_uuid
    assert result["status"] == gv.Result.failure
    assert "IntegrityError" in result["message"]
    """

    wrong_payload = {}
    with pytest.raises(Exception):
        await events_handler.on_sensors_data(engine_sid, [wrong_payload])


@pytest.mark.asyncio
async def test_on_actuator_data(
        mock_dispatcher: MockAsyncDispatcher,
        events_handler: DispatcherBasedGaiaEvents,
        ecosystem_aware_db: AsyncSQLAlchemyWrapper,
):
    await events_handler.on_actuator_data(engine_sid, [actuator_state_payload])
    async with ecosystem_aware_db.scoped_session() as session:
        logged_light_state = (
            await ActuatorStatus.get(
                session, ecosystem_uid=ecosystem_uid, actuator_type="light")
        )
        assert logged_light_state.actuator_type == ActuatorType.light
        assert logged_light_state.active == light_state["active"]
        assert logged_light_state.mode == light_state["mode"]
        assert logged_light_state.status == light_state["status"]

    wrong_payload = {}
    with pytest.raises(Exception):
        await events_handler.on_sensors_data(engine_sid, [wrong_payload])


@pytest.mark.asyncio
async def test_on_health_data(
        mock_dispatcher: MockAsyncDispatcher,
        events_handler: DispatcherBasedGaiaEvents,
        ecosystem_aware_db: AsyncSQLAlchemyWrapper,
):
    await events_handler.on_health_data(engine_sid, [health_data_payload])

    async with ecosystem_aware_db.scoped_session() as session:
        health_record = (await session.execute(select(HealthRecord))).scalar()
        assert health_record.timestamp == health_data.timestamp
        assert health_record.green == health_data.green
        assert health_record.necrosis == health_data.necrosis
        assert health_record.health_index == health_data.index

    wrong_payload = {}
    with pytest.raises(Exception):
        await events_handler.on_health_data(engine_sid, [wrong_payload])


@pytest.mark.asyncio
async def test_on_light_data(
        mock_dispatcher: MockAsyncDispatcher,
        events_handler: DispatcherBasedGaiaEvents,
        ecosystem_aware_db: AsyncSQLAlchemyWrapper,
):
    await events_handler.on_light_data(engine_sid, [light_data_payload])

    async with ecosystem_aware_db.scoped_session() as session:
        light = await Lighting.get(session, ecosystem_uid)
        assert light.method == light_data["method"]
        assert light.morning_start == light_data["morning_start"]
        assert light.morning_end == light_data["morning_end"]
        assert light.evening_start == light_data["evening_start"]
        assert light.evening_end == light_data["evening_end"]

    wrong_payload = {}
    with pytest.raises(Exception):
        await events_handler.on_light_data(engine_sid, [wrong_payload])


@pytest.mark.asyncio
async def test_turn_light(
        mock_dispatcher: MockAsyncDispatcher,
        events_handler: DispatcherBasedGaiaEvents
):
    await events_handler.turn_light(engine_sid, turn_actuator_payload)
    validated_data = TurnActuatorPayload(**turn_actuator_payload).model_dump()
    emitted = mock_dispatcher.emit_store[0]
    assert emitted["event"] == "turn_actuator"
    assert emitted["data"] == validated_data
    assert emitted["namespace"] == "gaia"

    wrong_payload = {}
    with pytest.raises(Exception):
        await events_handler.turn_light(engine_sid, wrong_payload)


@pytest.mark.asyncio
async def test_turn_actuator(mock_dispatcher: MockAsyncDispatcher, events_handler: DispatcherBasedGaiaEvents):
    await events_handler.turn_actuator(engine_sid, turn_actuator_payload)
    validated_data = TurnActuatorPayload(**turn_actuator_payload).model_dump()
    emitted = mock_dispatcher.emit_store[0]
    assert emitted["event"] == "turn_actuator"
    assert emitted["data"] == validated_data
    assert emitted["namespace"] == "gaia"

    wrong_payload = {}
    with pytest.raises(Exception):
        await events_handler.turn_actuator(engine_sid, wrong_payload)
