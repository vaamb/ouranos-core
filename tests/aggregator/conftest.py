from __future__ import annotations

import pytest
import pytest_asyncio

from sqlalchemy_wrapper import AsyncSQLAlchemyWrapper

import gaia_validators as gv

from ouranos.aggregator.events import GaiaEvents
from ouranos.aggregator.sky_watcher import SkyWatcher
from ouranos.core.database.init import create_base_data
from ouranos.core.database.models.gaia import Ecosystem, Engine, Hardware

import tests.data.gaia as g_data
from tests.utils import MockAsyncDispatcher


@pytest.fixture(scope="module")
def mock_aggregator():
    class MockAggregator:
        event_handler = None
        sky_watcher = None

    return MockAggregator()


@pytest.fixture(scope="module")
def sky_watcher(mock_aggregator):
    sky_watcher = SkyWatcher()
    mock_aggregator.sky_watcher = sky_watcher
    yield sky_watcher
    if sky_watcher.started:
        sky_watcher.stop()


@pytest.fixture(scope="module")
def mock_dispatcher():
    mock_dispatcher = MockAsyncDispatcher("aggregator")
    return mock_dispatcher


@pytest.fixture(scope="module")
def events_handler_module(mock_aggregator, mock_dispatcher: MockAsyncDispatcher):
    events_handler = GaiaEvents(mock_aggregator)  # noqa
    mock_aggregator.event_handler = events_handler
    events_handler.internal_dispatcher = mock_dispatcher
    events_handler.stream_dispatcher = mock_dispatcher
    mock_dispatcher.register_event_handler(events_handler)
    return events_handler


@pytest.fixture(scope="function")
def events_handler(
        mock_dispatcher: MockAsyncDispatcher,
        events_handler_module: GaiaEvents,
):
    mock_dispatcher._sessions[g_data.engine_sid] = {
        "engine_uid": g_data.engine_uid,
        "init_data": set()
    }
    yield events_handler_module
    mock_dispatcher.clear_store()
