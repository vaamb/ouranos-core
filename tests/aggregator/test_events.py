from __future__ import annotations

from asyncio import sleep
from copy import copy
from datetime import datetime,timedelta, timezone

import pytest
from sqlalchemy import select

import gaia_validators as gv
from sqlalchemy_wrapper import AsyncSQLAlchemyWrapper

from ouranos.aggregator.events import GaiaEvents
from ouranos.core.database.models.gaia import (
    ActuatorState, Ecosystem, Engine, EnvironmentParameter,
    Hardware, HealthRecord, Lighting, Place, SensorAlarm, SensorDataCache,
    SensorDataRecord)
from ouranos.core.exceptions import NotRegisteredError
from ouranos.core.utils import create_time_window

import tests.data.gaia as g_data
from tests.utils import MockAsyncDispatcher


def test_handler(
        mock_dispatcher: MockAsyncDispatcher,
        events_handler: GaiaEvents
):
    assert events_handler._dispatcher == mock_dispatcher
    assert events_handler.namespace == "gaia"
    assert len(mock_dispatcher.emit_store) == 0


@pytest.mark.asyncio
async def test_registration_wrapper(
        mock_dispatcher: MockAsyncDispatcher,
        events_handler: GaiaEvents
):
    await events_handler.on_ping(g_data.engine_sid, [
        {"uid": g_data.ecosystem_uid, "status": True}
    ])

    # Remove sid from session dict
    mock_dispatcher._sessions[g_data.engine_sid] = {}
    with pytest.raises(NotRegisteredError):
        await events_handler.on_ping(g_data.engine_sid, [
            {"uid": g_data.ecosystem_uid, "status": True}
        ])


@pytest.mark.asyncio
async def test_on_connect(
        mock_dispatcher: MockAsyncDispatcher,
        events_handler: GaiaEvents
):
    await events_handler.on_connect(g_data.engine_sid, "")
    emitted = mock_dispatcher.emit_store[0]
    assert emitted["event"] == "register"
    assert emitted["data"] is None


@pytest.mark.asyncio
async def test_on_disconnect(
        mock_dispatcher: MockAsyncDispatcher,
        events_handler: GaiaEvents,
        engine_aware_db: AsyncSQLAlchemyWrapper  # noqa
):
    await events_handler.on_disconnect(g_data.engine_sid)

    assert mock_dispatcher._sessions[g_data.engine_sid] == {}

    emitted = mock_dispatcher.emit_store[0]
    assert emitted["event"] == "ecosystem_status"
    assert emitted["data"] == {}
    assert emitted["namespace"] == "application-internal"


@pytest.mark.asyncio
async def test_on_register_engine(
        mock_dispatcher: MockAsyncDispatcher,
        events_handler: GaiaEvents,
        naive_db: AsyncSQLAlchemyWrapper,
):
    payload = gv.EnginePayload(
        engine_uid=g_data.engine_uid,
        address=g_data.ip_address
    ).model_dump()
    await events_handler.on_register_engine(g_data.engine_sid, payload)
    emitted = mock_dispatcher.emit_store[0]
    assert emitted["event"] == "registration_ack"
    assert emitted["namespace"] == "gaia"
    assert emitted["room"] == g_data.engine_sid
    assert mock_dispatcher._sessions[g_data.engine_sid]["engine_uid"] == g_data.engine_uid

    async with naive_db.scoped_session() as session:
        engine = await Engine.get(session, uid=g_data.engine_uid)
        assert engine.uid == g_data.engine_uid
        assert engine.address == g_data.ip_address

    wrong_payload = {}
    with pytest.raises(Exception):
        await events_handler.on_register_engine(g_data.engine_sid, wrong_payload)


@pytest.mark.asyncio
async def test_on_ping(
        mock_dispatcher: MockAsyncDispatcher,
        events_handler: GaiaEvents,
        engine_aware_db: AsyncSQLAlchemyWrapper,
):
    async with engine_aware_db.scoped_session() as session:
        engine = await Engine.get(session, uid=g_data.engine_uid)
        start = copy(engine.last_seen)
    await sleep(0.1)

    await events_handler.on_ping(g_data.engine_sid, [
        {"uid": g_data.ecosystem_uid, "status": True}
    ])

    async with engine_aware_db.scoped_session() as session:
        engine = await Engine.get_by_id(session, engine_id=g_data.engine_uid)
        assert engine.last_seen > start


@pytest.mark.asyncio
async def test_on_base_info(
        mock_dispatcher: MockAsyncDispatcher,
        events_handler: GaiaEvents,
        naive_db: AsyncSQLAlchemyWrapper,
):
    await events_handler.on_base_info(g_data.engine_sid, [g_data.base_info_payload])
    emitted = mock_dispatcher.emit_store[0]
    assert emitted["event"] == "ecosystem_status"
    assert emitted["data"] == [
        {"status": g_data.base_info["status"], 'uid': g_data.base_info["uid"]}
    ]
    assert emitted["namespace"] == "application-internal"

    async with naive_db.scoped_session() as session:
        ecosystem = await Ecosystem.get(session, uid=g_data.ecosystem_uid)
        assert ecosystem.engine_uid == g_data.base_info["engine_uid"]
        assert ecosystem.name == g_data.base_info["name"]
        assert ecosystem.status == g_data.base_info["status"]

    wrong_payload = {}
    with pytest.raises(Exception):
        await events_handler.on_base_info(g_data.engine_sid, [wrong_payload])


@pytest.mark.asyncio
async def test_on_management(
        mock_dispatcher: MockAsyncDispatcher,
        events_handler: GaiaEvents,
        ecosystem_aware_db: AsyncSQLAlchemyWrapper,
):
    await events_handler.on_management(g_data.engine_sid, [g_data.management_payload])

    management_value = 0
    for management in gv.ManagementFlags:
        try:
            if g_data.management_data[management.name]:
                management_value += management.value
        except KeyError:
            pass

    async with ecosystem_aware_db.scoped_session() as session:
        ecosystem = await Ecosystem.get(session, uid=g_data.ecosystem_uid)
        assert ecosystem.management == management_value

    wrong_payload = {}
    with pytest.raises(Exception):
        await events_handler.on_management(g_data.engine_sid, [wrong_payload])


@pytest.mark.asyncio
async def test_on_environmental_parameters(
        mock_dispatcher: MockAsyncDispatcher,
        events_handler: GaiaEvents,
        ecosystem_aware_db: AsyncSQLAlchemyWrapper,
):
    await events_handler.on_environmental_parameters(
        g_data.engine_sid, [g_data.environmental_payload])

    async with ecosystem_aware_db.scoped_session() as session:
        ecosystem = await Ecosystem.get(session, uid=g_data.ecosystem_uid)
        assert ecosystem.day_start == g_data.sky["day"]
        assert ecosystem.night_start == g_data.sky["night"]

        light = await Lighting.get(session, ecosystem_uid=g_data.ecosystem_uid)
        assert light.method == g_data.sky["lighting"]

        environment_parameter = await EnvironmentParameter.get(
            session, ecosystem_uid=g_data.ecosystem_uid, parameter=g_data.climate["parameter"])
        assert environment_parameter.day == g_data.climate["day"]
        assert environment_parameter.night == g_data.climate["night"]
        assert environment_parameter.hysteresis == g_data.climate["hysteresis"]

    wrong_payload = {}
    with pytest.raises(Exception):
        await events_handler.on_environmental_parameters(g_data.engine_sid, [wrong_payload])


@pytest.mark.asyncio
async def test_on_hardware(
        mock_dispatcher: MockAsyncDispatcher,
        events_handler: GaiaEvents,
        ecosystem_aware_db: AsyncSQLAlchemyWrapper,
):
    await events_handler.on_hardware(g_data.engine_sid, [g_data.hardware_payload])

    async with ecosystem_aware_db.scoped_session() as session:
        hardware = await Hardware.get(session, uid=g_data.hardware_data["uid"])
        assert hardware.name == g_data.hardware_data["name"]
        assert hardware.level.name == g_data.hardware_data["level"]
        assert hardware.address == g_data.hardware_data["address"]
        assert hardware.type.name == g_data.hardware_data["type"]
        assert hardware.model == g_data.hardware_data["model"]
        measures = [f"{measure.name}|{measure.unit}" for measure in hardware.measures]
        measures.sort()
        measures_data = copy(g_data.hardware_data["measures"])
        measures_data.sort()
        assert measures == measures_data

    wrong_payload = {}
    with pytest.raises(Exception):
        await events_handler.on_hardware(g_data.engine_sid, [wrong_payload])


@pytest.mark.asyncio
async def test_on_sensors_data(
        mock_dispatcher: MockAsyncDispatcher,
        events_handler: GaiaEvents,
        ecosystem_aware_db: AsyncSQLAlchemyWrapper,
):
    await events_handler.on_sensors_data(g_data.engine_sid, [g_data.sensors_data_payload])
    emitted = mock_dispatcher.emit_store[0]
    assert emitted["event"] == "current_sensors_data"
    assert emitted["data"] == [{
        'ecosystem_uid': g_data.sensors_data_payload["uid"],
        'sensor_uid': g_data.sensor_record.sensor_uid,
        'measure': g_data.sensor_record.measure,
        'timestamp': g_data.sensors_data["timestamp"],
        'value': g_data.sensor_record.value
    }]
    assert emitted["namespace"] == "application-internal"

    async with ecosystem_aware_db.scoped_session() as session:
        sensor_data = (await SensorDataCache.get_recent(session))[0]
        assert sensor_data.measure == g_data.sensor_record.measure
        assert sensor_data.value == g_data.sensor_record.value
        assert sensor_data.timestamp == g_data.sensors_data["timestamp"]

    alarm_data = events_handler.alarms_data[0]
    assert alarm_data["sensor_uid"] == g_data.alarm_record.sensor_uid
    assert alarm_data["measure"] == g_data.alarm_record.measure
    assert alarm_data["position"] == g_data.alarm_record.position
    assert alarm_data["delta"] == g_data.alarm_record.delta
    assert alarm_data["level"] == g_data.alarm_record.level

    wrong_payload = {}
    with pytest.raises(Exception):
        await events_handler.on_sensors_data(g_data.engine_sid, [wrong_payload])


@pytest.mark.asyncio
async def test_log_sensors_data(
        mock_dispatcher: MockAsyncDispatcher,
        events_handler: GaiaEvents,
        ecosystem_aware_db: AsyncSQLAlchemyWrapper,
):
    # Cache new data (rely on `test_on_sensors_data`)
    await events_handler.on_sensors_data(g_data.engine_sid, [g_data.sensors_data_payload])
    await events_handler.log_sensors_data()

    async with ecosystem_aware_db.scoped_session() as session:
        sensor_data = (
            await SensorDataRecord.get_records(
                session,
                sensor_uid=g_data.hardware_uid,
                measure_name=g_data.measure_name,
                time_window=create_time_window(
                    start_time=datetime.now(timezone.utc) - timedelta(hours=1),
                    end_time=datetime.now(timezone.utc) + timedelta(hours=1),
                ),
            )
        )[0]
        assert sensor_data.ecosystem_uid == g_data.sensors_data_payload["uid"]
        assert sensor_data.sensor_uid == g_data.sensor_record.sensor_uid
        assert sensor_data.measure == g_data.sensor_record.measure
        assert sensor_data.value == g_data.sensor_record.value
        assert sensor_data.timestamp == g_data.sensors_data["timestamp"]

        alarm_data = await SensorAlarm.get_recent(
            session, sensor_uid=g_data.hardware_uid, measure=g_data.measure_name)
        assert alarm_data.ecosystem_uid == g_data.sensors_data_payload["uid"]
        assert alarm_data.sensor_uid == g_data.alarm_record.sensor_uid
        assert alarm_data.measure == g_data.alarm_record.measure
        assert alarm_data.position == g_data.alarm_record.position
        assert alarm_data.delta == g_data.alarm_record.delta
        assert alarm_data.level == g_data.alarm_record.level
        assert alarm_data.timestamp_from == g_data.sensors_data["timestamp"]
        assert alarm_data.timestamp_to == g_data.sensors_data["timestamp"]


@pytest.mark.asyncio
async def test_on_places_list(
        mock_dispatcher: MockAsyncDispatcher,
        events_handler: GaiaEvents,
        engine_aware_db: AsyncSQLAlchemyWrapper,
):
    await events_handler.on_places_list(
        g_data.engine_sid, g_data.places_payload)

    async with engine_aware_db.scoped_session() as session:
        place = await Place.get(
            session,
            engine_uid=g_data.engine_uid,
            name=g_data.place_dict.name,
        )
        assert place.longitude == g_data.place_dict.coordinates.longitude
        assert place.latitude == g_data.place_dict.coordinates.latitude


@pytest.mark.asyncio
async def test_on_buffered_sensors_data(
        mock_dispatcher: MockAsyncDispatcher,
        events_handler: GaiaEvents,
        ecosystem_aware_db: AsyncSQLAlchemyWrapper,
):
    await events_handler.on_buffered_sensors_data(
        g_data.engine_sid, g_data.buffered_data_payload)
    emitted = mock_dispatcher.emit_store[0]
    assert emitted["namespace"] == "gaia"
    assert emitted["room"] == g_data.engine_sid
    assert emitted["event"] == "buffered_data_ack"
    result: gv.RequestResultDict = emitted["data"]
    assert result["uuid"] == g_data.request_uuid
    assert result["status"] == gv.Result.success

    async with ecosystem_aware_db.scoped_session() as session:
        temperature_data = (
            await SensorDataRecord.get_records(
                session,
                sensor_uid=g_data.hardware_uid,
                measure_name="temperature",
                time_window=create_time_window(
                    end_time=datetime.now(timezone.utc) + timedelta(days=1))
            )
        )[0]
        assert temperature_data.ecosystem_uid == \
               g_data.buffered_data_temperature.ecosystem_uid
        assert temperature_data.sensor_uid == g_data.buffered_data_temperature.sensor_uid
        assert temperature_data.measure == g_data.buffered_data_temperature.measure
        assert temperature_data.value == g_data.buffered_data_temperature.value
        assert temperature_data.timestamp == g_data.buffered_data_temperature.timestamp

    # TODO: fix as it currently doesn't fail but yet doesn't save duplicate
    """
    # Resend same data to have an integrity error
    await events_handler.on_buffered_sensors_data(g_data.engine_sid, buffered_data_payload)
    emitted = mock_dispatcher.emit_store[0]
    assert emitted["namespace"] == "gaia"
    assert emitted["room"] == g_data.engine_sid
    assert emitted["event"] == "buffered_data_ack"
    result: gv.RequestResultDict = emitted["data"]
    assert result["uuid"] == request_uuid
    assert result["status"] == gv.Result.failure
    assert "IntegrityError" in result["message"]
    """

    wrong_payload = {}
    with pytest.raises(Exception):
        await events_handler.on_sensors_data(g_data.engine_sid, [wrong_payload])


@pytest.mark.asyncio
async def test_on_actuators_data(
        mock_dispatcher: MockAsyncDispatcher,
        events_handler: GaiaEvents,
        ecosystem_aware_db: AsyncSQLAlchemyWrapper,
):
    await events_handler.on_actuators_data(
        g_data.engine_sid, [g_data.actuator_state_payload])
    async with ecosystem_aware_db.scoped_session() as session:
        logged_light_state = (
            await ActuatorState.get(
                session, ecosystem_uid=g_data.ecosystem_uid, type=gv.HardwareType.light)
        )
        assert logged_light_state.type == gv.HardwareType.light
        assert logged_light_state.active == g_data.light_state.active
        assert logged_light_state.mode == g_data.light_state.mode
        assert logged_light_state.status == g_data.light_state.status

    wrong_payload = {}
    with pytest.raises(Exception):
        await events_handler.on_sensors_data(g_data.engine_sid, [wrong_payload])


@pytest.mark.asyncio
async def test_on_health_data(
        mock_dispatcher: MockAsyncDispatcher,
        events_handler: GaiaEvents,
        ecosystem_aware_db: AsyncSQLAlchemyWrapper,
):
    await events_handler.on_health_data(g_data.engine_sid, [g_data.health_data_payload])

    async with ecosystem_aware_db.scoped_session() as session:
        stmt = select(HealthRecord)
        result = await session.execute(stmt)
        health_record = result.scalar()
        assert health_record.timestamp == g_data.health_data.timestamp
        assert health_record.green == g_data.health_data.green
        assert health_record.necrosis == g_data.health_data.necrosis
        assert health_record.health_index == g_data.health_data.index

    wrong_payload = {}
    with pytest.raises(Exception):
        await events_handler.on_health_data(g_data.engine_sid, [wrong_payload])


@pytest.mark.asyncio
async def test_on_light_data(
        mock_dispatcher: MockAsyncDispatcher,
        events_handler: GaiaEvents,
        ecosystem_aware_db: AsyncSQLAlchemyWrapper,
):
    await events_handler.on_light_data(g_data.engine_sid, [g_data.light_data_payload])

    async with ecosystem_aware_db.scoped_session() as session:
        light = await Lighting.get(session, ecosystem_uid=g_data.ecosystem_uid)
        assert light.method == g_data.light_data["method"]
        assert light.morning_start == g_data.light_data["morning_start"]
        assert light.morning_end == g_data.light_data["morning_end"]
        assert light.evening_start == g_data.light_data["evening_start"]
        assert light.evening_end == g_data.light_data["evening_end"]

    wrong_payload = {}
    with pytest.raises(Exception):
        await events_handler.on_light_data(g_data.engine_sid, [wrong_payload])


@pytest.mark.asyncio
async def test_turn_light(
        mock_dispatcher: MockAsyncDispatcher,
        events_handler: GaiaEvents
):
    await events_handler.turn_light(g_data.engine_sid, g_data.turn_actuator_payload)
    validated_data = gv.TurnActuatorPayload(**g_data.turn_actuator_payload).model_dump()
    emitted = mock_dispatcher.emit_store[0]
    assert emitted["event"] == "turn_actuator"
    assert emitted["data"] == validated_data
    assert emitted["namespace"] == "gaia"

    wrong_payload = {}
    with pytest.raises(Exception):
        await events_handler.turn_light(g_data.engine_sid, wrong_payload)


@pytest.mark.asyncio
async def test_turn_actuator(
        mock_dispatcher: MockAsyncDispatcher,
        events_handler: GaiaEvents
):
    await events_handler.turn_actuator(g_data.engine_sid, g_data.turn_actuator_payload)
    validated_data = gv.TurnActuatorPayload(**g_data.turn_actuator_payload).model_dump()
    emitted = mock_dispatcher.emit_store[0]
    assert emitted["event"] == "turn_actuator"
    assert emitted["data"] == validated_data
    assert emitted["namespace"] == "gaia"

    wrong_payload = {}
    with pytest.raises(Exception):
        await events_handler.turn_actuator(g_data.engine_sid, wrong_payload)
