import asyncio

import httpx
import pytest

from fastapi import FastAPI
from socketio import AsyncManager
from uvicorn import Server

from ouranos.core.config import ConfigDict, ImmutableDict
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
        assert web_server.app.started is True

        # Test double startup
        with pytest.raises(RuntimeError):
            await web_server.complete_startup()

        # Test complete_shutdown
        await web_server.complete_shutdown()
        assert not web_server.started
        assert web_server.common_resources_state.used_by == 0
        assert web_server.app.started is False

        # Test double shutdown
        with pytest.raises(RuntimeError):
            await web_server.complete_shutdown()

    async def test_lifecycle_multiprocess(self, config: ConfigDict):
        """Test that uvicorn's workers receive the config and serve requests.

        Workers are spawned in a fresh interpreter, so they only know the
        config handed to them through the app factory. Only a request proves
        they started: a worker failing at startup is respawned in a loop by
        uvicorn, and the startup itself still succeeds.
        """
        port = 5001
        multiprocess_config = ImmutableDict(
            {**config, "WEB_SERVER_WORKERS": 1, "API_PORT": port})
        web_server = WebServer(multiprocess_config)

        await web_server.complete_startup()
        try:
            async with httpx.AsyncClient() as client:
                response: httpx.Response | None = None
                # Spawning a worker and importing Ouranos takes a few seconds
                for _ in range(100):
                    try:
                        response = await client.get(
                            f"http://127.0.0.1:{port}/api/app/version")
                        break
                    except httpx.TransportError:
                        await asyncio.sleep(0.1)
            assert response is not None, "No worker answered"
            assert response.status_code == 200
            assert response.json() == config["VERSION"]
        finally:
            await web_server.complete_shutdown()

        # The workers are stopped
        async with httpx.AsyncClient(timeout=1) as client:
            with pytest.raises(httpx.TransportError):
                await client.get(f"http://127.0.0.1:{port}/api/app/version")

    def test_create_app(self, config: ConfigDict):
        app = create_app(config)
        assert isinstance(app, FastAPI)

    def test_create_sio_manager(self):
        sio_manager = create_sio_manager()
        assert isinstance(sio_manager, AsyncManager)
