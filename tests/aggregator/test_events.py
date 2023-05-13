from __future__ import annotations

from typing import cast, TypedDict

import pytest
import pytest_asyncio

from dispatcher import AsyncDispatcher
from gaia_validators import TurnActuatorPayload
from sqlalchemy_wrapper import AsyncSQLAlchemyWrapper

from ouranos.aggregator.events import (
    DispatcherBasedGaiaEvents, SocketIOEnginePayload)
from ouranos.core.database.models.gaia import Engine
from ouranos.core.exceptions import NotRegisteredError

from .store import *


class EmitDict(TypedDict):
    event: str
    data: dict | list | str | tuple | None
    room: str
    namespace: str


@pytest_asyncio.fixture(scope="function")
async def engine_aware_db(setup_db: AsyncSQLAlchemyWrapper):
    async with setup_db.scoped_session() as session:
        engine_dict = {
            "uid": engine_uid,
            "sid": engine_sid,
            "registration_date": datetime.now(timezone.utc),
            "address": ip_address,
            "last_seen": datetime.now(timezone.utc),
        }
        await Engine.create(session, engine_dict)
    yield
    async with setup_db.scoped_session() as session:
        await Engine.delete(session, engine_uid)


@pytest.fixture(scope="module")
def mock_dispatcher():
    class MockAsyncDispatcher(AsyncDispatcher):
        asyncio_based = True

        def __init__(self, namespace: str):
            super().__init__(namespace)
            self.emit_store: list[EmitDict] = []

        async def emit(
                self,
                event: str,
                data: dict | list | str | tuple | None = None,
                to: dict | None = None,
                room: str | None = None,
                namespace: str | None = None,
                ttl: int | None = None,
                **kwargs
        ):
            self.emit_store.append(cast(EmitDict, {
                "event": event,
                "data": data,
                "room": room,
                "namespace": namespace,
            }))

        def clear_store(self):
            self.emit_store.clear()

        def start(self, loop=None) -> None:
            pass

    mock_dispatcher = MockAsyncDispatcher("aggregator")
    return mock_dispatcher


@pytest.fixture(scope="module")
def events_handler_module(mock_dispatcher):
    events_handler = DispatcherBasedGaiaEvents()
    events_handler.ouranos_dispatcher = mock_dispatcher
    mock_dispatcher.register_event_handler(events_handler)
    return events_handler


@pytest.fixture(scope="function")
def events_handler(mock_dispatcher, events_handler_module):
    mock_dispatcher._sessions[engine_sid] = {"engine_uid": engine_uid}
    yield events_handler_module
    mock_dispatcher.clear_store()


def test_handler(mock_dispatcher, events_handler: DispatcherBasedGaiaEvents):
    assert events_handler._dispatcher == mock_dispatcher
    assert events_handler.broker_type == "dispatcher"
    assert events_handler.namespace == "/gaia"
    assert len(mock_dispatcher.emit_store) == 0


@pytest.mark.asyncio
async def test_registration_wrapper(mock_dispatcher, events_handler: DispatcherBasedGaiaEvents):
    await events_handler.on_ping(engine_sid, [ecosystem_uid])

    # Remove sid from session dict
    mock_dispatcher._sessions[engine_sid] = {}
    with pytest.raises(NotRegisteredError):
        await events_handler.on_ping(engine_sid, [ecosystem_uid])


@pytest.mark.asyncio
async def test_on_connect(mock_dispatcher, events_handler: DispatcherBasedGaiaEvents):
    await events_handler.on_connect(engine_sid, "")
    emitted = mock_dispatcher.emit_store[0]
    assert emitted["event"] == "register"
    assert emitted["data"] is None


@pytest.mark.asyncio
async def test_on_disconnect(
        mock_dispatcher,
        events_handler: DispatcherBasedGaiaEvents,
        engine_aware_db
):
    await events_handler.on_disconnect(engine_sid)

    assert mock_dispatcher._sessions[engine_sid] == {}

    emitted = mock_dispatcher.emit_store[0]
    assert emitted["event"] == "ecosystem_status"
    assert emitted["data"] == {}
    assert emitted["namespace"] == "application"


@pytest.mark.asyncio
async def test_on_register_engine(mock_dispatcher, events_handler: DispatcherBasedGaiaEvents):
    payload = SocketIOEnginePayload(
        engine_uid=engine_uid,
        address=ip_address
    ).dict()
    await events_handler.on_register_engine(engine_sid, payload)
    emitted = mock_dispatcher.emit_store[0]
    assert emitted["event"] == "registration_ack"
    assert emitted["namespace"] == "gaia"
    assert emitted["room"] == engine_sid
    assert mock_dispatcher._sessions[engine_sid]["engine_uid"] == engine_uid

    wrong_payload = {}
    with pytest.raises(Exception):
        await events_handler.on_register_engine(engine_sid, wrong_payload)


@pytest.mark.asyncio
async def test_on_ping(mock_dispatcher, events_handler: DispatcherBasedGaiaEvents):
    await events_handler.on_ping(engine_sid, [ecosystem_uid])


@pytest.mark.asyncio
async def test_on_base_info(mock_dispatcher, events_handler: DispatcherBasedGaiaEvents):
    await events_handler.on_base_info(engine_sid, [base_info_payload])
    emitted = mock_dispatcher.emit_store[0]
    assert emitted["event"] == "ecosystem_status"
    assert emitted["data"] == [
        {"status": base_info["status"], 'uid': base_info["uid"]}
    ]
    assert emitted["namespace"] == "application"

    wrong_payload = {}
    with pytest.raises(Exception):
        await events_handler.on_base_info(engine_sid, [wrong_payload])


@pytest.mark.asyncio
async def test_on_management(mock_dispatcher, events_handler: DispatcherBasedGaiaEvents):
    await events_handler.on_management(engine_sid, [management_payload])

    wrong_payload = {}
    with pytest.raises(Exception):
        await events_handler.on_management(engine_sid, [wrong_payload])


@pytest.mark.asyncio
async def test_on_environmental_parameters(mock_dispatcher, events_handler: DispatcherBasedGaiaEvents):
    await events_handler.on_environmental_parameters(engine_sid, [environmental_payload])

    wrong_payload = {}
    with pytest.raises(Exception):
        await events_handler.on_environmental_parameters(engine_sid, [wrong_payload])


@pytest.mark.asyncio
async def test_on_hardware(mock_dispatcher, events_handler: DispatcherBasedGaiaEvents):
    await events_handler.on_hardware(engine_sid, [hardware_payload])

    wrong_payload = {}
    with pytest.raises(Exception):
        await events_handler.on_hardware(engine_sid, [wrong_payload])


@pytest.mark.asyncio
async def test_on_sensors_data(mock_dispatcher, events_handler: DispatcherBasedGaiaEvents):
    await events_handler.on_sensors_data(engine_sid, [sensors_data_payload])
    emitted = mock_dispatcher.emit_store[0]
    assert emitted["event"] == "current_sensors_data"
    assert emitted["data"] == sensors_data
    assert emitted["namespace"] == "application"

    wrong_payload = {}
    with pytest.raises(Exception):
        await events_handler.on_sensors_data(engine_sid, [wrong_payload])


@pytest.mark.asyncio
async def test_on_health_data(mock_dispatcher, events_handler: DispatcherBasedGaiaEvents):
    await events_handler.on_health_data(engine_sid, [health_data_payload])

    wrong_payload = {}
    with pytest.raises(Exception):
        await events_handler.on_health_data(engine_sid, [wrong_payload])


@pytest.mark.asyncio
async def test_on_light_data(mock_dispatcher, events_handler: DispatcherBasedGaiaEvents):
    await events_handler.on_light_data(engine_sid, [light_data_payload])

    wrong_payload = {}
    with pytest.raises(Exception):
        await events_handler.on_light_data(engine_sid, [wrong_payload])


@pytest.mark.asyncio
async def test_turn_light(mock_dispatcher, events_handler: DispatcherBasedGaiaEvents):
    await events_handler.turn_light(engine_sid, turn_actuator_payload)
    validated_data = TurnActuatorPayload(**turn_actuator_payload).dict()
    emitted = mock_dispatcher.emit_store[0]
    assert emitted["event"] == "turn_actuator"
    assert emitted["data"] == validated_data
    assert emitted["namespace"] == "gaia"

    wrong_payload = {}
    with pytest.raises(Exception):
        await events_handler.turn_light(engine_sid, wrong_payload)


@pytest.mark.asyncio
async def test_turn_actuator(mock_dispatcher, events_handler: DispatcherBasedGaiaEvents):
    await events_handler.turn_actuator(engine_sid, turn_actuator_payload)
    validated_data = TurnActuatorPayload(**turn_actuator_payload).dict()
    emitted = mock_dispatcher.emit_store[0]
    assert emitted["event"] == "turn_actuator"
    assert emitted["data"] == validated_data
    assert emitted["namespace"] == "gaia"

    wrong_payload = {}
    with pytest.raises(Exception):
        await events_handler.turn_actuator(engine_sid, wrong_payload)
