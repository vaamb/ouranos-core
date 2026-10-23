import asyncio

import httpx
import pytest

from fastapi import FastAPI
from socketio import AsyncManager
from uvicorn import Server
from uvicorn.config import STARTUP_FAILURE

from ouranos.core.config import ConfigDict, ImmutableDict
from ouranos.web_server.factory import create_app, create_sio_manager
from ouranos.web_server.main import _create_app_or_exit, WebServer


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

    async def test_startup_failure(self, config: ConfigDict, monkeypatch):
        """A failing `create_app` makes the startup raise instead of hanging."""
        def create_app(_config):
            raise ValueError("Broken app")

        monkeypatch.setattr("ouranos.web_server.main.create_app", create_app)
        web_server = WebServer(config)

        with pytest.raises(ValueError, match="Broken app"):
            await asyncio.wait_for(web_server.app.start(), timeout=5)
        assert web_server.app.started is False

    async def test_startup_failure_multiprocess(self, config: ConfigDict):
        """A worker failing at startup makes the startup raise without leaving
        uvicorn's supervisor running, which would hang the process at exit.

        Depending on how long the worker takes to import Ouranos, uvicorn
        either notices its `STARTUP_FAILURE` (`RuntimeError`) or still waits
        for it when the startup times out (`TimeoutError`).
        """
        port = 5002
        multiprocess_config = ImmutableDict({
            **config, "WEB_SERVER_WORKERS": 1, "API_PORT": port,
            # Only read in the worker, where `create_sio_manager()` raises
            "SIO_MANAGER_URL": "unsupported://",
        })
        web_server = WebServer(multiprocess_config)

        with pytest.raises((RuntimeError, TimeoutError)):
            await web_server.app.start()
        assert web_server.app.started is False

        # The socket is released
        with pytest.raises(OSError):
            await asyncio.open_connection("127.0.0.1", port)

    def test_create_app_or_exit(self, config: ConfigDict, monkeypatch):
        """A worker failing in `create_app` exits with `STARTUP_FAILURE`, so
        uvicorn stops instead of respawning it forever."""
        def create_app(_config):
            raise ValueError("Broken app")

        monkeypatch.setattr("ouranos.web_server.main.create_app", create_app)

        with pytest.raises(SystemExit) as exc_info:
            _create_app_or_exit(config)
        assert exc_info.value.code == STARTUP_FAILURE

    def test_create_app(self, config: ConfigDict):
        app = create_app(config)
        assert isinstance(app, FastAPI)

    def test_create_sio_manager(self):
        sio_manager = create_sio_manager()
        assert isinstance(sio_manager, AsyncManager)
