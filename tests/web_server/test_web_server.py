import pytest

from fastapi import FastAPI
from socketio import AsyncManager
from uvicorn import Server

from ouranos.core.config import ConfigDict
from ouranos.web_server.factory import create_app, create_sio_manager
from ouranos.web_server.main import WebServer


@pytest.mark.asyncio
class TestWebServer:
    async def test_lifecycle(self, config: ConfigDict):
        """Test the complete lifecycle of an Aggregator instance.

        Verifies:
        - Proper initialization of the functionality
        - Successful startup sequence (initialize → startup)
        - Proper shutdown sequence (shutdown → post_shutdown)
        - Error handling for double startup/shutdown attempts
        """

        web_server = WebServer(config)

        # Test complete_startup
        await web_server.complete_startup()
        assert web_server.started
        assert web_server.common_resources_state.used_by == 1
        assert isinstance(web_server.server, Server)
        assert web_server.server.started is True

        # Test double startup
        with pytest.raises(RuntimeError):
            await web_server.complete_startup()

        # Test complete_shutdown
        await web_server.complete_shutdown()
        assert not web_server.started
        assert web_server.common_resources_state.used_by == 0
        assert web_server.server.started is False

        # Test double shutdown
        with pytest.raises(RuntimeError):
            await web_server.complete_shutdown()

    def test_create_app(self):
        app = create_app()
        assert isinstance(app, FastAPI)

    def test_create_sio_manager(self):
        sio_manager = create_sio_manager()
        assert isinstance(sio_manager, AsyncManager)
