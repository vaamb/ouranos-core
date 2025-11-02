from __future__ import annotations

from asyncio import sleep
from copy import copy, deepcopy
from datetime import datetime,timedelta, timezone
import os
from pathlib import Path
from unittest.mock import patch
from uuid import UUID

import numpy as np
import pytest
from sqlalchemy import delete

from dispatcher import AsyncDispatcher
import gaia_validators as gv
from gaia_validators.image import SerializableImage, SerializableImagePayload
from sqlalchemy_wrapper import AsyncSQLAlchemyWrapper

from ouranos import current_app, json
from ouranos.aggregator.events import GaiaEvents
from ouranos.aggregator.sky_watcher import SkyWatcher
from ouranos.core.database.models.gaia import (
    ActuatorRecord, ActuatorState, Chaos, CrudRequest, Ecosystem, Engine,
    EnvironmentParameter, Hardware, NycthemeralCycle, Place, Plant, SensorAlarm,
    SensorDataCache, SensorDataRecord, WeatherEvent)
from ouranos.core.exceptions import NotRegisteredError
from ouranos.core.utils import create_time_window

from tests.class_fixtures import EcosystemAware, EngineAware, HardwareAware
import tests.data.gaia as g_data
from tests.utils import MockAsyncDispatcher


@pytest.mark.asyncio
class TestHandler:
    def test_init(
            self,
            mock_dispatcher: MockAsyncDispatcher,
            events_handler: GaiaEvents
    ):
        """Test the basic initialization and properties of the GaiaEvents handler.

        Verifies that:
        - The handler is properly initialized with the provided dispatcher
        - The namespace is correctly set to "gaia"
        - The internal and stream dispatchers are properly initialized
        - The camera directory is correctly set up
        """
        # Test basic initialization
        assert events_handler._dispatcher == mock_dispatcher
        assert events_handler.namespace == "gaia"
        assert len(mock_dispatcher.emit_store) == 0

        # Test initial state
        assert isinstance(events_handler._internal_dispatcher, AsyncDispatcher)
        assert isinstance(events_handler._stream_dispatcher, AsyncDispatcher)
        assert events_handler._alarms_data == []

        # Test camera directory initialization
        expected_camera_dir = Path(current_app.static_dir) / "camera_stream"
        assert str(events_handler.camera_dir) == str(expected_camera_dir)

    async def test_on_connect(
            self,
            mock_dispatcher: MockAsyncDispatcher,
            events_handler: GaiaEvents
    ):
        """Test the on_connect event handler.

        Verifies that:
        - A register event is emitted with the correct parameters
        """
        await events_handler.on_connect("sid", {})
        emitted = mock_dispatcher.emit_store[0]
        assert emitted["event"] == "register"

    async def test_on_disconnect(
            self,
            mock_dispatcher: MockAsyncDispatcher,
            events_handler: GaiaEvents
    ):
        """Test the on_disconnect event handler.

        Verifies that:
        - The session is properly cleaned up
        - Ecosystem status is updated to disconnected
        - Correct event is emitted with the updated status
        """
        await events_handler.on_disconnect("sid")


@pytest.mark.asyncio
class TestEngineRegistration:
    async def test_on_register_engine(
            self,
            mock_dispatcher: MockAsyncDispatcher,
            events_handler: GaiaEvents,
            db: AsyncSQLAlchemyWrapper,
    ):
        """Test the engine registration process.

        Verifies that:
        - The "init_data" store session is properly initialized
        - Registration acknowledgment is sent back to the engine
        - Camera token is sent back to the engine
        - Engine information is stored in the session
        - Engine details are saved to the database
        - Invalid payloads raise appropriate exceptions
        """
        payload = gv.EnginePayload(
            engine_uid=g_data.engine_uid,
            address=g_data.ip_address
        ).model_dump()

        # Call the method
        await events_handler.on_register_engine(g_data.engine_sid, payload)

        # Verify the session
        async with events_handler.session(g_data.engine_sid) as session:
            assert session["engine_uid"] == g_data.engine_uid
            assert session["init_data"] == {
                "base_info", "chaos_parameters", "nycthemeral_info",
                "climate", "weather", "hardware", "plants", "management",
                "actuators_data",
            }

        # Verify the re emitted events
        assert len(mock_dispatcher.emit_store) == 2

        emitted = mock_dispatcher.emit_store.popleft()
        assert emitted["event"] == "registration_ack"
        assert emitted["namespace"] == "gaia"
        assert emitted["room"] == g_data.engine_sid

        emitted = mock_dispatcher.emit_store.popleft()
        assert emitted["event"] == "camera_token"
        assert emitted["namespace"] == "gaia"
        assert emitted["room"] == g_data.engine_sid

        # Verify that the data has been logged
        async with db.scoped_session() as session:
            engine = await Engine.get(session, uid=g_data.engine_uid)
            assert engine.uid == g_data.engine_uid
            assert engine.address == g_data.ip_address

        wrong_payload = {}
        with pytest.raises(Exception):
            await events_handler.on_register_engine(g_data.engine_sid, wrong_payload)


@pytest.mark.asyncio
class TestEngineBackground(EngineAware):
    async def test_on_ping(
            self,
            mock_dispatcher: MockAsyncDispatcher,
            events_handler: GaiaEvents,
            db: AsyncSQLAlchemyWrapper,
    ):
        """Test the ping handler for engine heartbeats.

        Verifies that:
        - The engine's last_seen timestamp is updated on ping
        """
        async with db.scoped_session() as session:
            engine = await Engine.get(session, uid=g_data.engine_uid)
            start = engine.last_seen
        await sleep(0.1)

        payload: gv.EnginePingPayloadDict = {
            "engine_uid": g_data.engine_uid,
            "timestamp": datetime.now(timezone.utc),
            "ecosystems": [],
        }
        await events_handler.on_ping(g_data.engine_sid, payload)

        async with db.scoped_session() as session:
            engine = await Engine.get_by_id(session, engine_id=g_data.engine_uid)
            assert engine.last_seen > start

    async def test_registration_wrapper(
            self,
            mock_dispatcher: MockAsyncDispatcher,
            events_handler: GaiaEvents,
            db: AsyncSQLAlchemyWrapper,
    ):
        """Test the registration wrapper functionality.

        Verifies that:
        - The handler properly processes engine pings
        - Proper error is raised when session is not registered
        """
        payload: gv.EnginePingPayloadDict = {
            "engine_uid": g_data.engine_uid,
            "timestamp": datetime.now(timezone.utc),
            "ecosystems": [],
        }
        await events_handler.on_ping(g_data.engine_sid, payload)

        # Remove sid from session dict
        mock_dispatcher._sessions[g_data.engine_sid] = {}
        with pytest.raises(NotRegisteredError):
            await events_handler.on_ping(g_data.engine_sid, [])


@pytest.mark.asyncio
class TestStartInitializationDataExchange(EngineAware):
    async def test_on_places_list(
            self,
            mock_dispatcher: MockAsyncDispatcher,
            events_handler: GaiaEvents,
            db: AsyncSQLAlchemyWrapper,
    ):
        """Test handling of place information.

        Verifies that:
        - Place information is correctly stored in the database
        - Geographic coordinates are properly saved
        - Place data is associated with the correct engine
        """
        await events_handler.on_places_list(
            g_data.engine_sid, g_data.places_payload)

        async with db.scoped_session() as session:
            place = await Place.get(
                session,
                engine_uid=g_data.engine_uid,
                name=g_data.place_dict.name,
            )
            assert place.longitude == g_data.place_dict.coordinates.longitude
            assert place.latitude == g_data.place_dict.coordinates.latitude

    async def test_on_base_info(
            self,
            mock_dispatcher: MockAsyncDispatcher,
            events_handler: GaiaEvents,
            db: AsyncSQLAlchemyWrapper,
    ):
        """Test handling of ecosystem base information.

        Verifies that:
        - Ecosystem status event is emitted with correct data
        - Session init_data is properly cleared
        - Ecosystem data is correctly saved to the database
        - Invalid payloads raise appropriate exceptions
        """
        # Set up the session with init_data
        async with events_handler.session(g_data.engine_sid) as session:
            session["init_data"] = {"base_info"}

        # Call the method
        await events_handler.on_base_info(g_data.engine_sid, [g_data.base_info_payload])

        # Verify the re emitted event
        assert len(mock_dispatcher.emit_store) == 1
        emitted = mock_dispatcher.emit_store[0]
        assert emitted["event"] == "ecosystem_status"
        assert emitted["data"] == [
            {"status": g_data.base_info["status"], "uid": g_data.base_info["uid"]}
        ]
        assert emitted["namespace"] == "application-internal"

        # Verify the session
        async with events_handler.session(g_data.engine_sid) as session:
            assert not session["init_data"]

        # Verify that the data has been logged
        async with db.scoped_session() as session:
            ecosystem = await Ecosystem.get(session, uid=g_data.ecosystem_uid)
            assert ecosystem.engine_uid == g_data.base_info["engine_uid"]
            assert ecosystem.name == g_data.base_info["name"]
            assert ecosystem.status == g_data.base_info["status"]

        # Verify that the wrong payload raises an exception
        wrong_payload = {}
        with pytest.raises(Exception):
            await events_handler.on_base_info(g_data.engine_sid, [wrong_payload])


@pytest.mark.asyncio
class TestInitializationDataExchange(EcosystemAware):
    async def test_on_management(
            self,
            mock_dispatcher: MockAsyncDispatcher,
            events_handler: GaiaEvents,
            db: AsyncSQLAlchemyWrapper,
    ):
        """Test handling of ecosystem management settings.

        Verifies that:
        - Management event is emitted with correct data
        - Session init_data is properly cleared
        - Management flags are correctly calculated and stored
        - Invalid payloads raise appropriate exceptions
        """
        # Set up the session with init_data
        async with events_handler.session(g_data.engine_sid) as session:
            session["init_data"] = {"management"}

        # Call the method
        await events_handler.on_management(g_data.engine_sid, [g_data.management_payload])

        # Verify the re emitted event
        assert len(mock_dispatcher.emit_store) == 1
        emitted = mock_dispatcher.emit_store[0]
        assert emitted["event"] == "management"
        assert emitted["data"] == [g_data.management_payload]
        assert emitted["namespace"] == "application-internal"

        # Verify the session
        async with events_handler.session(g_data.engine_sid) as session:
            assert not session["init_data"]

        # Compute the expected management flag value
        management_value = 0
        for management in gv.ManagementFlags:
            try:
                if g_data.management_data[management.name]:
                    management_value += management.value
            except KeyError:
                pass

        # Verify that the data has been logged
        async with db.scoped_session() as session:
            ecosystem = await Ecosystem.get(session, uid=g_data.ecosystem_uid)
            assert ecosystem.management == management_value

        # Verify that the wrong payload raises an exception
        with pytest.raises(Exception):
            await events_handler.on_management(g_data.engine_sid, [{}])

    async def test_on_chaos_parameters(
            self,
            mock_dispatcher: MockAsyncDispatcher,
            events_handler: GaiaEvents,
            db: AsyncSQLAlchemyWrapper,
    ):
        """Test handling of chaos parameters for an ecosystem.

        Verifies that:
        - Chaos parameters event is emitted with correct data
        - Session init_data is properly cleared
        - Chaos parameters are correctly stored in the database
        - Invalid payloads raise appropriate exceptions
        """
        # Set up the session with init_data
        async with events_handler.session(g_data.engine_sid) as session:
            session["init_data"] = {"chaos_parameters"}

        # Call the method
        await events_handler.on_chaos_parameters(
            g_data.engine_sid, [g_data.chaos_payload])

        # Verify the re emitted event
        assert len(mock_dispatcher.emit_store) == 1
        emitted = mock_dispatcher.emit_store[0]
        assert emitted["event"] == "chaos_parameters"
        assert emitted["data"] == [g_data.chaos_payload]
        assert emitted["namespace"] == "application-internal"

        # Verify the session
        async with events_handler.session(g_data.engine_sid) as session:
            assert not session["init_data"]

        # Verify that the data has been logged
        async with db.scoped_session() as session:
            chaos = await Chaos.get(session, ecosystem_uid=g_data.ecosystem_uid)
            assert chaos.ecosystem_uid == g_data.ecosystem_uid
            assert chaos.frequency == g_data.chaos["frequency"]
            assert chaos.intensity == g_data.chaos["intensity"]
            assert chaos.duration == g_data.chaos["duration"]
            assert chaos.beginning is None
            assert chaos.end is None

        # Verify that the wrong payload raises an exception
        with pytest.raises(Exception):
            await events_handler.on_management(g_data.engine_sid, [{}])

    async def test_on_nycthemeral_info(
            self,
            mock_dispatcher: MockAsyncDispatcher,
            events_handler: GaiaEvents,
            db: AsyncSQLAlchemyWrapper,
    ):
        """Test handling of nycthemeral (day/night cycle) information.

        Verifies that:
        - Nycthemeral info event is emitted with correct data
        - Session init_data is properly cleared
        - Lighting cycle data is correctly stored in the database
        - Target lighting settings are properly handled
        - Invalid payloads raise appropriate exceptions
        """
        # Set up the session with init_data
        async with events_handler.session(g_data.engine_sid) as session:
            session["init_data"] = {"nycthemeral_info"}

        # Call the method
        await events_handler.on_nycthemeral_info(
            g_data.engine_sid, [g_data.nycthemeral_info_payload])

        # Verify the re emitted event
        assert len(mock_dispatcher.emit_store) == 1
        emitted = mock_dispatcher.emit_store[0]
        assert emitted["event"] == "nycthemeral_info"
        truncated_payload = deepcopy(g_data.nycthemeral_info_payload)
        truncated_payload["data"].pop("target")
        assert emitted["data"] == [truncated_payload]
        assert emitted["namespace"] == "application-internal"

        # Verify the session
        async with events_handler.session(g_data.engine_sid) as session:
            assert not session["init_data"]

        # Verify that the data has been logged
        async with db.scoped_session() as session:
            lighting = await NycthemeralCycle.get(session, ecosystem_uid=g_data.ecosystem_uid)
            assert lighting.ecosystem_uid == g_data.ecosystem_uid
            assert lighting.span == g_data.sky["span"]
            assert lighting.lighting == g_data.sky["lighting"]
            assert lighting.target is None
            assert lighting.day == g_data.sky["day"]
            assert lighting.night == g_data.sky["night"]

        # Verify that the wrong payload raises an exception
        with pytest.raises(Exception):
            await events_handler.on_nycthemeral_info(g_data.engine_sid, [{}])

    async def test_on_climate(
            self,
            mock_dispatcher: MockAsyncDispatcher,
            events_handler: GaiaEvents,
            db: AsyncSQLAlchemyWrapper,
    ):
        """Test handling of climate control parameters.

        Verifies that:
        - Session init_data is properly cleared
        - Climate parameters are correctly stored in the database
        - No events are emitted (as per design)
        - Invalid payloads raise appropriate exceptions
        """
        # Set up the session with init_data
        async with events_handler.session(g_data.engine_sid) as session:
            session["init_data"] = {"climate"}

        # Call the method
        await events_handler.on_climate(
            g_data.engine_sid, [g_data.climate_payload])

        # There is no re emitted event

        # Verify the session
        async with events_handler.session(g_data.engine_sid) as session:
            assert not session["init_data"]

        # Verify that the data has been logged
        async with db.scoped_session() as session:
            environment_parameter = await EnvironmentParameter.get(
                session, ecosystem_uid=g_data.ecosystem_uid, parameter=g_data.climate["parameter"])
            assert environment_parameter.day == g_data.climate["day"]
            assert environment_parameter.night == g_data.climate["night"]
            assert environment_parameter.hysteresis == g_data.climate["hysteresis"]
            assert environment_parameter.linked_actuator_group_increase.name == \
                   g_data.climate["linked_actuators"]["increase"]
            assert environment_parameter.linked_actuator_group_decrease.name == \
                   g_data.climate["linked_actuators"]["decrease"]
            assert environment_parameter.linked_measure.name == \
                   g_data.climate["linked_measure"]

        # Verify that the wrong payload raises an exception
        with pytest.raises(Exception):
            await events_handler.on_climate(g_data.engine_sid, [{}])

    async def test_on_weather(
            self,
            mock_dispatcher: MockAsyncDispatcher,
            events_handler: GaiaEvents,
            db: AsyncSQLAlchemyWrapper,
    ):
        """Test handling of weather information.

        Verifies that:
        - Session init_data is properly cleared
        - Weather details are correctly stored in the database
        - Weather measures are properly associated
        - No events are emitted (as per design)
        - Invalid payloads raise appropriate exceptions
        """
        # Set up the session with init_data
        async with events_handler.session(g_data.engine_sid) as session:
            session["init_data"] = {"weather"}

        # Call the method
        await events_handler.on_weather(g_data.engine_sid, [g_data.weather_payload])

        # There is no re emitted event

        # Verify the session
        async with events_handler.session(g_data.engine_sid) as session:
            assert not session["init_data"]

        # Verify that the data has been logged
        async with db.scoped_session() as session:
            weather = await WeatherEvent.get(
                session, ecosystem_uid=g_data.ecosystem_uid, parameter=g_data.weather["parameter"])
            assert weather.pattern == g_data.weather["pattern"]
            assert weather.duration == g_data.weather["duration"]
            assert weather.level == g_data.weather["level"]
            assert weather.linked_actuator == g_data.weather["linked_actuator"]

        # Verify that the wrong payload raises an exception
        with pytest.raises(Exception):
            await events_handler.on_weather(g_data.engine_sid, [{}])

    async def test_on_hardware(
            self,
            mock_dispatcher: MockAsyncDispatcher,
            events_handler: GaiaEvents,
            db: AsyncSQLAlchemyWrapper,
    ):
        """Test handling of hardware information.

        Verifies that:
        - Session init_data is properly cleared
        - Hardware details are correctly stored in the database
        - Hardware measures are properly associated
        - No events are emitted (as per design)
        - Invalid payloads raise appropriate exceptions
        """
        # Set up the session with init_data
        async with events_handler.session(g_data.engine_sid) as session:
            session["init_data"] = {"hardware"}

        # Call the method
        await events_handler.on_hardware(g_data.engine_sid, [g_data.hardware_payload])

        # There is no re emitted event

        # Verify the session
        async with events_handler.session(g_data.engine_sid) as session:
            assert not session["init_data"]

        # Verify that the data has been logged
        async with db.scoped_session() as session:
            # Test single attributes
            hardware = await Hardware.get(session, uid=g_data.hardware_data["uid"])
            assert hardware.name == g_data.hardware_data["name"]
            assert hardware.level.name == g_data.hardware_data["level"]
            assert hardware.address == g_data.hardware_data["address"]
            assert hardware.type.name == g_data.hardware_data["type"]
            assert hardware.model == g_data.hardware_data["model"]
            # Test measures
            measures = [f"{measure.name}|{measure.unit}" for measure in hardware.measures]
            measures.sort()
            measures_data = copy(g_data.hardware_data["measures"])
            measures_data.sort()
            assert measures == measures_data
            # Test groups
            groups = [g.name for g in hardware.groups]
            groups.sort()
            assert "__type__" not in groups
            groups_data = [*g_data.hardware_data["groups"]]
            groups_data.sort()
            if "__type__" in groups_data:
                groups_data[groups_data.index("__type__")] = hardware.type.name
            assert groups == groups_data

        # Verify that the wrong payload raises an exception
        with pytest.raises(Exception):
            await events_handler.on_hardware(g_data.engine_sid, [{}])

    async def test_on_plants(
            self,
            mock_dispatcher: MockAsyncDispatcher,
            events_handler: GaiaEvents,
            db: AsyncSQLAlchemyWrapper,
    ):
        """Test handling of hardware information.

        Verifies that:
        - Session init_data is properly cleared
        - Hardware details are correctly stored in the database before
        - Plants details are correctly stored in the database
        - Plants hardware are properly associated
        - No events are emitted (as per design)
        - Invalid payloads raise appropriate exceptions
        """
        # Set up the session with init_data
        async with events_handler.session(g_data.engine_sid) as session:
            session["init_data"] = {"plants"}

        async with db.scoped_session() as session:
            hardware = await Hardware.get(session, uid=g_data.hardware_data["uid"])
            if hardware:
                await Hardware.delete(session, uid=g_data.hardware_uid)

        # Call the method with hardware missing from the DB
        with pytest.raises(RuntimeError):
            await events_handler.on_plants(g_data.engine_sid, [g_data.plants_payload])

        # Add the hardware to the DB
        async with db.scoped_session() as session:
            hardware_data = gv.HardwareConfig(**g_data.hardware_data).model_dump()
            del hardware_data["uid"]
            del hardware_data["multiplexer_model"]
            del hardware_data["groups"]
            hardware_data["ecosystem_uid"] = g_data.ecosystem_uid
            await Hardware.create(session, uid=g_data.hardware_uid, values=hardware_data)

        # Call the method
        await events_handler.on_plants(g_data.engine_sid, [g_data.plants_payload])

        # There is no re emitted event

        # Verify the session
        async with events_handler.session(g_data.engine_sid) as session:
            assert not session["init_data"]

        # Verify that the data has been logged
        async with db.scoped_session() as session:
            plant = await Plant.get(session, uid=g_data.plant_data["uid"])
            assert plant.name == g_data.plant_data["name"]
            assert plant.species == g_data.plant_data["species"]
            assert plant.sowing_date == g_data.plant_data["sowing_date"]
            assert plant.hardware[0].uid == g_data.hardware_data["uid"]

        # Verify that the wrong payload raises an exception
        with pytest.raises(Exception):
            await events_handler.on_plant(g_data.engine_sid, [{}])

    async def test_on_actuators_data(
            self,
            mock_dispatcher: MockAsyncDispatcher,
            events_handler: GaiaEvents,
            db: AsyncSQLAlchemyWrapper,
    ):
        """Test handling of real-time actuator data.

        Verifies that:
        - Actuator data event is emitted with correct data
        - Session init_data is properly cleared
        - Actuator states are correctly stored
        - Multiple actuator types are handled properly
        - Invalid payloads raise appropriate exceptions
        """
        # Set up the session with init_data
        async with events_handler.session(g_data.engine_sid) as session:
            session["init_data"] = {"actuators_data"}

        # Call the method
        await events_handler.on_actuators_data(
            g_data.engine_sid, [g_data.actuator_state_payload])

        # Verify the re emitted event
        assert len(mock_dispatcher.emit_store) == 1
        emitted = mock_dispatcher.emit_store[0]
        assert emitted["event"] == "actuators_data"
        assert len(emitted["data"]) == 6
        assert emitted["namespace"] == "application-internal"

        # Verify that the session has been updated
        async with events_handler.session(g_data.engine_sid) as session:
            assert not session["init_data"]

        # Verify that the data has been logged
        async with db.scoped_session() as session:
            logged_light_state = (
                await ActuatorState.get(
                    session, ecosystem_uid=g_data.ecosystem_uid, type=gv.HardwareType.light)
            )
            assert logged_light_state.type == gv.HardwareType.light
            assert logged_light_state.active == g_data.light_state.active
            assert logged_light_state.mode == g_data.light_state.mode
            assert logged_light_state.status == g_data.light_state.status

        # Verify that the wrong payload raises an exception
        with pytest.raises(Exception):
            await events_handler.on_actuators_data(g_data.engine_sid, [{}])


@pytest.mark.asyncio
class TestEcosystemBackground(HardwareAware):
    async def test_on_ping(
            self,
            mock_dispatcher: MockAsyncDispatcher,
            events_handler: GaiaEvents,
            db: AsyncSQLAlchemyWrapper,
    ):
        """Test the ping handler for engine heartbeats.

        Verifies that:
        - The engine's last_seen timestamp is updated on ping
        - The ecosystem status is properly processed
        """
        async with db.scoped_session() as session:
            engine = await Engine.get(session, uid=g_data.engine_uid)
            start_engine = copy(engine.last_seen)
            ecosystem = await Ecosystem.get(session, uid=g_data.ecosystem_uid)
            start_ecosystem = ecosystem.last_seen
        await sleep(0.1)

        payload: gv.EnginePingPayloadDict = {
            "engine_uid": g_data.engine_uid,
            "timestamp": datetime.now(timezone.utc),
            "ecosystems": [
                {"uid": g_data.ecosystem_uid, "status": True},
            ],
        }
        await events_handler.on_ping(g_data.engine_sid, payload)

        async with db.scoped_session() as session:
            engine = await Engine.get_by_id(session, engine_id=g_data.engine_uid)
            assert engine.last_seen > start_engine
            ecosystem = await Ecosystem.get(session, uid=g_data.ecosystem_uid)
            assert ecosystem.last_seen > start_ecosystem

    async def test_on_sensors_data(
            self,
            mock_dispatcher: MockAsyncDispatcher,
            events_handler: GaiaEvents,
            db: AsyncSQLAlchemyWrapper,
    ):
        """Test handling of real-time sensor data.

        Verifies that:
        - Current sensor data event is emitted with correct data
        - Sensor data is properly cached
        - Alarms are processed and stored
        - Data is properly formatted in the emitted event
        - Invalid payloads raise appropriate exceptions
        """
        await events_handler.on_sensors_data(g_data.engine_sid, [g_data.sensors_data_payload])

        emitted = mock_dispatcher.emit_store[0]
        assert emitted["event"] == "current_sensors_data"
        assert emitted["data"] == [{
            "ecosystem_uid": g_data.sensors_data_payload["uid"],
            "sensor_uid": g_data.sensor_record.sensor_uid,
            "measure": g_data.sensor_record.measure,
            "timestamp": g_data.sensors_data["timestamp"],
            "value": g_data.sensor_record.value
        }]
        assert emitted["namespace"] == "application-internal"

        async with db.scoped_session() as session:
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

        # Test new payload
        new_payload = deepcopy(g_data.sensors_data_payload)
        new_payload["data"]["records"][0] = gv.SensorRecord(
            g_data.hardware_uid, g_data.measure_name, 21, None)

        await events_handler.on_sensors_data(g_data.engine_sid, [new_payload])

        emitted = mock_dispatcher.emit_store[1]
        assert emitted["event"] == "current_sensors_data"
        assert emitted["data"] == [{
            "ecosystem_uid": g_data.sensors_data_payload["uid"],
            "sensor_uid": g_data.sensor_record.sensor_uid,
            "measure": g_data.sensor_record.measure,
            "timestamp": g_data.sensors_data["timestamp"],
            "value": 21
        }]

        # Verify the cache, it should have been updated
        async with db.scoped_session() as session:
            sensor_data = (await SensorDataCache.get_recent(session))[0]
            assert sensor_data.value == 21

        # Test wrong payload
        wrong_payload = {}
        with pytest.raises(Exception):
            await events_handler.on_sensors_data(g_data.engine_sid, [wrong_payload])

        # Clear the cache
        async with db.scoped_session() as session:
            await SensorDataCache.clear(session)

    async def test_log_sensors_data(
            self,
            mock_dispatcher: MockAsyncDispatcher,
            events_handler: GaiaEvents,
            db: AsyncSQLAlchemyWrapper,
    ):
        """Test logging of sensor data to persistent storage.

        Verifies that:
        - Cached sensor data is properly logged to the database
        - Alarm data is properly associated with sensor readings
        - Timestamps are correctly preserved
        - Data integrity is maintained during the logging process
        """
        # Cache new data (rely on `test_on_sensors_data`)
        # Clear sensor data cache, then populate it without calling the sensors data event, then continue
        await events_handler.on_sensors_data(g_data.engine_sid, [g_data.sensors_data_payload])
        await events_handler.log_sensors_data()

        async with db.scoped_session() as session:
            sensor_data = (
                await SensorDataRecord.get_records(
                    session,
                    sensor_uid=g_data.hardware_uid,
                    measure=g_data.measure_name,
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

        async with db.scoped_session() as session:
            await SensorDataCache.clear(session)
            await session.execute(delete(SensorDataRecord))

    async def test_on_health_data(
            self,
            mock_dispatcher: MockAsyncDispatcher,
            events_handler: GaiaEvents,
            db: AsyncSQLAlchemyWrapper,
    ):
        """Test handling of ecosystem health data.

        Verifies that:
        - Health data is properly stored in the database
        - Sensor readings are correctly associated with ecosystems
        - Timestamps and values are preserved
        - Invalid payloads raise appropriate exceptions
        """
        await events_handler.on_health_data(
            g_data.engine_sid, [g_data.health_data_payload])

        async with db.scoped_session() as session:
            health_record = await SensorDataRecord.get(
                session, ecosystem_uid=g_data.ecosystem_uid,
                sensor_uid=g_data.health_record.sensor_uid)
            assert health_record.ecosystem_uid == g_data.health_data_payload["uid"]
            assert health_record.sensor_uid == g_data.health_record.sensor_uid
            assert health_record.measure == g_data.health_record.measure
            assert health_record.timestamp == g_data.health_record.timestamp
            assert health_record.value == g_data.health_record.value

        wrong_payload = {}
        with pytest.raises(Exception):
            await events_handler.on_health_data(g_data.engine_sid, [wrong_payload])

    async def test_on_light_data(
            self,
            mock_dispatcher: MockAsyncDispatcher,
            events_handler: GaiaEvents,
            db: AsyncSQLAlchemyWrapper,
    ):
        """Test handling of lighting schedule data.

        Verifies that:
        - Lighting schedule is correctly stored in the database
        - Morning and evening time windows are properly saved
        - Data is associated with the correct ecosystem
        - Invalid payloads raise appropriate exceptions
        """
        await events_handler.on_light_data(g_data.engine_sid, [g_data.light_data_payload])

        async with db.scoped_session() as session:
            light = await NycthemeralCycle.get(session, ecosystem_uid=g_data.ecosystem_uid)
            assert light.morning_start == g_data.light_data["morning_start"]
            assert light.morning_end == g_data.light_data["morning_end"]
            assert light.evening_start == g_data.light_data["evening_start"]
            assert light.evening_end == g_data.light_data["evening_end"]

        wrong_payload = {}
        with pytest.raises(Exception):
            await events_handler.on_light_data(g_data.engine_sid, [wrong_payload])

    async def test_turn_light(
            self,
            mock_dispatcher: MockAsyncDispatcher,
            events_handler: GaiaEvents
    ):
        """Test the turn_light command handler.

        Verifies that:
        - The turn_actuator event is emitted with correct parameters
        - Payload is properly validated and formatted
        - The event is emitted to the correct namespace
        """
        await events_handler.turn_light(g_data.engine_sid, g_data.turn_actuator_payload)
        validated_data = gv.TurnActuatorPayload(**g_data.turn_actuator_payload).model_dump()
        emitted = mock_dispatcher.emit_store[0]
        assert emitted["event"] == "turn_actuator"
        assert emitted["data"] == validated_data
        assert emitted["namespace"] == "gaia"

        wrong_payload = {}
        with pytest.raises(Exception):
            await events_handler.turn_light(g_data.engine_sid, wrong_payload)

    async def test_turn_actuator(
            self,
            mock_dispatcher: MockAsyncDispatcher,
            events_handler: GaiaEvents
    ):
        """Test the generic turn_actuator command handler.

        Verifies that:
        - The turn_actuator event is emitted with correct parameters
        - Different actuator types are handled correctly
        - Payload validation works as expected
        - The event is emitted to the correct namespace
        """
        await events_handler.turn_actuator(g_data.engine_sid, g_data.turn_actuator_payload)
        validated_data = gv.TurnActuatorPayload(**g_data.turn_actuator_payload).model_dump()
        emitted = mock_dispatcher.emit_store[0]
        assert emitted["event"] == "turn_actuator"
        assert emitted["data"] == validated_data
        assert emitted["namespace"] == "gaia"

        wrong_payload = {}
        with pytest.raises(Exception):
            await events_handler.turn_actuator(g_data.engine_sid, wrong_payload)

    async def test_crud(
            self,
            mock_dispatcher: MockAsyncDispatcher,
            events_handler: GaiaEvents,
            db: AsyncSQLAlchemyWrapper,
    ):
        """Test the CRUD operation request handling.

        Verifies that the crud method correctly processes a CRUD request by:
        1. Creating a CRUD request record in the database
        2. Emitting a 'crud' event to the target engine
        3. Including the correct routing and action information
        """
        # Test data
        test_uuid = "12345678-1234-5678-1234-567812345678"
        test_action = "create"
        test_target = "hardware"
        test_data = {"key": "value"}

        # Create test payload
        crud_payload = {
            "uuid": test_uuid,
            "routing": {
                "engine_uid": g_data.engine_uid,
                "ecosystem_uid": g_data.ecosystem_uid
            },
            "action": test_action,
            "target": test_target,
            "data": test_data
        }

        # Call the method
        await events_handler.crud(g_data.engine_sid, crud_payload)

        # Verify the re emitted event
        assert len(mock_dispatcher.emit_store) == 1
        emitted = mock_dispatcher.emit_store[0]
        assert emitted["event"] == "crud"
        assert emitted["namespace"] == "gaia"
        assert emitted["data"] == crud_payload

        # Verify the CRUD request was created in the database
        async with db.scoped_session() as session:
            crud_request = await CrudRequest.get(session, uuid=UUID(test_uuid))
            assert crud_request is not None
            assert crud_request.engine_uid == g_data.engine_uid
            assert crud_request.ecosystem_uid == g_data.ecosystem_uid
            assert crud_request.action == test_action
            assert crud_request.target == test_target
            assert crud_request.payload == json.dumps(test_data)

            # Cleanup
            await session.delete(crud_request)
            await session.commit()

    async def test_on_crud_result(
            self,
            mock_dispatcher: MockAsyncDispatcher,
            events_handler: GaiaEvents,
            db: AsyncSQLAlchemyWrapper,
    ):
        """Test the handling of CRUD operation results.

        Verifies that the on_crud_result method correctly processes and stores the result
        of a CRUD operation by:
        1. Creating a test CRUD request in the database
        2. Simulating a CRUD result with a success status and message
        3. Verifying the CRUD request is updated with the provided status and message
        4. Cleaning up the test data
        """
        # Setup: Create a test CRUD request in the database
        test_uuid = UUID("12345678-1234-5678-1234-567812345678")
        test_status = "success"
        test_message = "Operation completed successfully"

        # Create a test CRUD request
        async with db.scoped_session() as session:
            await CrudRequest.create(
                session,
                uuid=test_uuid,
                values={
                    "engine_uid": g_data.engine_uid,
                    "ecosystem_uid": g_data.ecosystem_uid,
                    "action": "create",
                    "target": "hardware",
                    "payload": "{}",
                },
            )
            await session.commit()

        # Call the method with test data
        test_data = {
            "uuid": str(test_uuid),
            "status": test_status,
            "message": test_message,
        }
        await events_handler.on_crud_result(g_data.engine_sid, test_data)

        # Verify the CRUD request was updated
        async with db.scoped_session() as session:
            updated_request = await CrudRequest.get(session, uuid=test_uuid)
            assert updated_request.result == test_status
            assert updated_request.message == test_message

            # Cleanup
            await session.delete(updated_request)
            await session.commit()


@pytest.mark.asyncio
class TestBufferedDataExchange(HardwareAware):
    async def test_on_buffered_sensors_data(
            self,
            mock_dispatcher: MockAsyncDispatcher,
            events_handler: GaiaEvents,
            db: AsyncSQLAlchemyWrapper,
    ):
        """Test handling of buffered sensor data batches.

        Verifies that:
        - Buffered sensor data is properly processed
        - Acknowledgment is sent back to the sender
        - Data is correctly stored in the database
        - Duplicate data handling works as expected
        - Invalid payloads raise appropriate exceptions
        """
        # Handle unique buffered data
        await events_handler.on_buffered_sensors_data(
            g_data.engine_sid, g_data.buffered_data_payload)

        emitted = mock_dispatcher.emit_store[0]
        assert emitted["namespace"] == "gaia"
        assert emitted["room"] == g_data.engine_sid
        assert emitted["event"] == "buffered_data_ack"
        result: gv.RequestResultDict = emitted["data"]
        assert result["uuid"] == g_data.request_uuid
        assert result["status"] == gv.Result.success

        async with db.scoped_session() as session:
            temperature_data = await SensorDataRecord.get_records(
                session,
                sensor_uid=g_data.hardware_uid,
                measure="temperature",
                time_window=create_time_window(
                    end_time=datetime.now(timezone.utc) + timedelta(days=1))
            )
            assert len(temperature_data) == 1
            temperature_data = temperature_data[0]

            assert temperature_data.ecosystem_uid == \
                   g_data.buffered_data_temperature.ecosystem_uid
            assert temperature_data.sensor_uid == g_data.buffered_data_temperature.sensor_uid
            assert temperature_data.measure == g_data.buffered_data_temperature.measure
            assert temperature_data.value == g_data.buffered_data_temperature.value
            assert temperature_data.timestamp == g_data.buffered_data_temperature.timestamp

        # Test duplicate data handling
        await events_handler.on_buffered_sensors_data(
            g_data.engine_sid, g_data.buffered_data_payload)

        emitted = mock_dispatcher.emit_store[0]
        assert emitted["namespace"] == "gaia"
        assert emitted["room"] == g_data.engine_sid
        assert emitted["event"] == "buffered_data_ack"
        result: gv.RequestResultDict = emitted["data"]
        assert result["uuid"] == g_data.request_uuid
        assert result["status"] == gv.Result.success

        async with db.scoped_session() as session:
            temperature_data = await SensorDataRecord.get_records(
                session,
                sensor_uid=g_data.hardware_uid,
                measure="temperature",
                time_window=create_time_window(
                    end_time=datetime.now(timezone.utc) + timedelta(days=1))
            )
            # Make sure we only have one record for temperature
            assert len(temperature_data) == 1

        wrong_payload = {}
        with pytest.raises(Exception):
            await events_handler.on_sensors_data(g_data.engine_sid, [wrong_payload])

    async def test_on_buffered_actuators_data(
            self,
            mock_dispatcher: MockAsyncDispatcher,
            events_handler: GaiaEvents,
            db: AsyncSQLAlchemyWrapper,
    ):
        """Test handling of buffered actuator data batches.

        Verifies that:
        - Buffered actuator data is properly processed
        - Acknowledgment is sent back to the sender
        - Actuator states are correctly stored in the database
        - Different actuator modes and statuses are handled
        - Invalid payloads raise appropriate exceptions
        """
        # Create test data for buffered actuators
        now = datetime.now(timezone.utc)
        buffered_actuator_data = gv.BufferedActuatorsStatePayloadDict(
            uuid=g_data.request_uuid,
            data=[
                gv.BufferedActuatorRecord(
                    ecosystem_uid=g_data.ecosystem_uid,
                    type=g_data.light_state.type,
                    group=g_data.light_state.group,
                    active=True,
                    mode=gv.ActuatorMode.manual,
                    status=True,
                    level=75.5,
                    timestamp=now,
                )
            ],
        )

        # Call the method
        await events_handler.on_buffered_actuators_data(
            g_data.engine_sid, buffered_actuator_data)

        # Verify the re emitted event
        emitted = mock_dispatcher.emit_store[0]
        assert emitted["namespace"] == "gaia"
        assert emitted["room"] == g_data.engine_sid
        assert emitted["event"] == "buffered_data_ack"
        result: gv.RequestResultDict = emitted["data"]
        assert result["uuid"] == g_data.request_uuid
        assert result["status"] == gv.Result.success

        # Verify that the data has been logged
        async with db.scoped_session() as session:
            # Check if the actuator state was updated in the database
            actuator_records = await ActuatorRecord.get_multiple(
                session,
                ecosystem_uid=g_data.ecosystem_uid,
                type=gv.HardwareType.light,
                timestamp=now,
            )

            assert len(actuator_records) == 1
            actuator_record = actuator_records[0]
            assert actuator_record is not None
            assert actuator_record.active is True
            assert actuator_record.mode == gv.ActuatorMode.manual
            assert actuator_record.status is True
            assert actuator_record.level == 75.5

        # Verify that the wrong payload raises an exception
        with pytest.raises(Exception):
            await events_handler.on_buffered_actuators_data(g_data.engine_sid, [{}])

@pytest.mark.asyncio
class TestPicture:
    async def test_picture_arrays(
            self,
            mock_dispatcher: MockAsyncDispatcher,
            events_handler: GaiaEvents,
            db: AsyncSQLAlchemyWrapper,
    ):
        """Test the picture_arrays method.

        This test verifies that:
        1. The method correctly processes incoming picture data
        2. Saves the image to the correct location
        3. Updates the database with the image metadata
        4. Emits the correct event with the updated picture information
        """
        # Setup test data
        camera_uid = "test_camera_1"
        timestamp = datetime.now(timezone.utc)

        # Create a test image (2x2 RGB image)
        test_image_data = np.zeros((2, 2, 3), dtype=np.uint8)
        test_image_data[0, 0] = [255, 0, 0]    # Red
        test_image_data[0, 1] = [0, 255, 0]    # Green
        test_image_data[1, 0] = [0, 0, 255]    # Blue
        test_image_data[1, 1] = [255, 255, 0]  # Yellow

        # Create serializable image
        image = SerializableImage(
            array=test_image_data,
            metadata={
                "camera_uid": camera_uid,
                "timestamp": timestamp.isoformat(),
                "test_metadata": "test_value"
            }
        )

        # Create payload
        payload = SerializableImagePayload(
            uid=g_data.ecosystem_uid,
            data=[image]
        )

        # Call the method
        await events_handler.picture_arrays(
            sid=g_data.engine_sid,
            data=payload.serialize(),
        )

        # Verify the re emitted event
        assert len(mock_dispatcher.emit_store) > 0, "No events were emitted"
        picture_event = mock_dispatcher.emit_store[0]
        assert picture_event is not None, "picture_arrays event was not emitted"
        assert picture_event["namespace"] == "application-internal"
        assert picture_event["data"]["ecosystem_uid"] == g_data.ecosystem_uid
        assert len(picture_event["data"]["updated_pictures"]) == 1
        updated_pic = picture_event["data"]["updated_pictures"][0]
        assert updated_pic["camera_uid"] == camera_uid
        assert updated_pic["path"] == f"camera_stream/{g_data.ecosystem_uid}/{camera_uid}.jpeg"
        assert updated_pic["timestamp"] == timestamp

        # Verify that the image array was saved
        expected_image_path = events_handler.camera_dir / g_data.ecosystem_uid / f"{camera_uid}.jpeg"
        assert os.path.exists(expected_image_path), "Image file was not saved"

        # Verify that the metadata has been logged
        from ouranos.core.database.models.gaia import CameraPicture
        async with db.scoped_session() as session:
            picture = await CameraPicture.get(
                session,
                ecosystem_uid=g_data.ecosystem_uid,
                camera_uid=camera_uid
            )
            assert picture is not None, "Camera picture was not saved to database"
            assert picture.path == f"camera_stream/{g_data.ecosystem_uid}/{camera_uid}.jpeg"
            assert picture.dimension == [2, 2, 3]
            assert picture.depth == "uint8"
            assert picture.timestamp == timestamp
            assert picture.other_metadata == {"test_metadata": "test_value"}


@pytest.mark.asyncio
class TestEventServiceUpdate:
    async def test_update_service(
            self,
            mock_dispatcher: MockAsyncDispatcher,
            events_handler: GaiaEvents,
            sky_watcher: SkyWatcher,
    ):
        """Test the service update functionality.

        Verifies that:
        - Service updates are properly processed
        - SkyWatcher is notified of the update
        - Database is updated with the new service information
        - Appropriate events are emitted
        - Error conditions are handled gracefully
        """
        # Assert the sky watcher is not started
        assert events_handler.aggregator.sky_watcher is sky_watcher
        assert sky_watcher.started is False

        # Test updating weather service (valid service)
        await events_handler.update_service(
            sid=g_data.engine_sid,
            data={"name": "weather", "status": True},
        )

        # Verify the sky watcher was started
        assert sky_watcher.started is True

        # Test updating with an invalid service name
        with patch.object(events_handler.logger, "error") as mock_error:
            await events_handler.update_service(
                sid=g_data.engine_sid,
                data={"name": "wrong_service", "status": True},
            )
            # Verify error was logged for invalid service
            mock_error.assert_called_once_with(
                "Received an update for service 'wrong_service', but only the "
                "weather service is supported."
            )

        # Test stopping the weather service
        await events_handler.update_service(
            sid=g_data.engine_sid,
            data={"name": "weather", "status": False},
        )
        # Verify the sky watcher was stopped
        assert events_handler.aggregator.sky_watcher.started is False
