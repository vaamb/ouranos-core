from __future__ import annotations

import pytest
import pytest_asyncio

from sqlalchemy_wrapper import AsyncSQLAlchemyWrapper

from ouranos.aggregator.events import GaiaEvents
from ouranos.core.database.init import create_base_data
from ouranos.core.database.models.gaia import Engine, Ecosystem

import tests.data.gaia as g_data
from tests.utils import MockAsyncDispatcher


@pytest_asyncio.fixture(scope="function", autouse=True)
async def naive_db(db: AsyncSQLAlchemyWrapper):
    from ouranos.core.database import models  # noqa
    yield db
    await db.drop_all()
    await db.create_all()
    await create_base_data()


@pytest_asyncio.fixture(scope="function")
async def engine_aware_db(naive_db: AsyncSQLAlchemyWrapper):
    async with naive_db.scoped_session() as session:
        engine = g_data.engine_dict.copy()
        uid = engine.pop("uid")
        await Engine.create(session, uid=uid, values=engine)
    return naive_db


@pytest_asyncio.fixture(scope="function")
async def ecosystem_aware_db(naive_db: AsyncSQLAlchemyWrapper):
    async with naive_db.scoped_session() as session:
        ecosystem = {
            **g_data.ecosystem_dict,
            "day_start": g_data.sky["day"],
            "night_start": g_data.sky["night"],
        }
        uid = ecosystem.pop("uid")
        await Ecosystem.create(session, uid=uid, values=ecosystem)
    return naive_db


@pytest.fixture(scope="module")
def mock_dispatcher():
    mock_dispatcher = MockAsyncDispatcher("aggregator")
    return mock_dispatcher


@pytest.fixture(scope="module")
def events_handler_module(mock_dispatcher: MockAsyncDispatcher):
    events_handler = GaiaEvents()
    events_handler.internal_dispatcher = mock_dispatcher
    mock_dispatcher.register_event_handler(events_handler)
    return events_handler


@pytest.fixture(scope="function")
def events_handler(mock_dispatcher, events_handler_module):
    mock_dispatcher._sessions[g_data.engine_sid] = {
        "engine_uid": g_data.engine_uid,
        "init_data": {
            "base_info", "environmental_parameters", "hardware", "management",
            "actuator_data", "light_data",
        }
    }
    yield events_handler_module
    mock_dispatcher.clear_store()
