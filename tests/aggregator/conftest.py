from __future__ import annotations

import pytest
import pytest_asyncio

from sqlalchemy_wrapper import AsyncSQLAlchemyWrapper

from ouranos.aggregator.events import DispatcherBasedGaiaEvents
from ouranos.core.database.models.gaia import Engine, Ecosystem

from ..utils import MockAsyncDispatcher
from .store import *


@pytest_asyncio.fixture(scope="function")
async def engine_aware_db(db: AsyncSQLAlchemyWrapper):
    async with db.scoped_session() as session:
        engine_dict = {
            "uid": engine_uid,
            "sid": engine_sid,
            "registration_date": (
                datetime.now(timezone.utc).replace(microsecond=0)
            ),
            "address": ip_address,
            "last_seen": datetime.now(timezone.utc),
        }
        await Engine.create(session, engine_dict)
    return db


@pytest_asyncio.fixture(scope="function")
async def ecosystem_aware_db(db: AsyncSQLAlchemyWrapper):
    async with db.scoped_session() as session:
        ecosystem_dict = {
            "engine_uid": engine_uid,
            "uid": ecosystem_uid,
            "name": ecosystem_name,
            "status": False,
            "registration_date": datetime.now(timezone.utc),
            "last_seen": datetime.now(timezone.utc),
            "management": 0,
        }
        await Ecosystem.create(session, ecosystem_dict)
    return db


@pytest.fixture(scope="module")
def mock_dispatcher():
    mock_dispatcher = MockAsyncDispatcher("aggregator")
    return mock_dispatcher


@pytest.fixture(scope="module")
def events_handler_module(mock_dispatcher: MockAsyncDispatcher):
    events_handler = DispatcherBasedGaiaEvents()
    events_handler.ouranos_dispatcher = mock_dispatcher
    mock_dispatcher.register_event_handler(events_handler)
    return events_handler


@pytest.fixture(scope="function")
def events_handler(mock_dispatcher, events_handler_module):
    mock_dispatcher._sessions[engine_sid] = {"engine_uid": engine_uid}
    yield events_handler_module
    mock_dispatcher.clear_store()
