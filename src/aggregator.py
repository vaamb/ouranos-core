from __future__ import annotations

import asyncio

from dispatcher import AsyncAMQPDispatcher, AsyncRedisDispatcher
from socketio import ASGIApp, AsyncServer
import uvicorn

import default
from src.core.communication.events import Events
from src.core.g import config as global_config


class Aggregator:
    def __init__(
            self,
            namespace: Events,
            config: dict | None = None
    ):
        self.config = config or global_config
        if not self.config:
            raise RuntimeError(
                "Either provide a config dict or set config globally with "
                "g.set_app_config"
            )
        self._namespace = namespace
        self._engine = None

    @property
    def engine(self) -> ASGIApp | AsyncAMQPDispatcher | AsyncRedisDispatcher:
        if self._engine is None:
            raise RuntimeError
        return self._engine

    @property
    def namespace(self) -> Events:
        return self._namespace

    def start(self) -> None:
        gaia_broker_url = self.config.get("GAIA_BROKER_URL",
                                          default.GAIA_BROKER_URL)
        if gaia_broker_url.startswith("socketio://"):
            if self.config.get("SERVER", default.FASTAPI):
                from src.app import sio
                sio.register_namespace(self._namespace)
                self._engine = sio
            else:
                sio = AsyncServer(async_mode='asgi', cors_allowed_origins=[])
                sio.register_namespace(self._namespace)
                self._engine = sio
                asgi_app = ASGIApp(sio)
                config = uvicorn.Config(
                    asgi_app,
                    port=5000,
                    server_header=False, date_header=False,
                )
                server = uvicorn.Server(config)
                asyncio.ensure_future(server.serve())
        elif gaia_broker_url.startswith("amqp://"):
            from dispatcher import AsyncAMQPDispatcher
            dispatcher = AsyncAMQPDispatcher("aggregator")
            dispatcher.register_event_handler(self._namespace)
            self._engine = dispatcher
            self._engine.start()
        elif gaia_broker_url.startswith("redis://"):
            from dispatcher import AsyncRedisDispatcher
            dispatcher = AsyncRedisDispatcher("aggregator")
            dispatcher.register_event_handler(self._namespace)
            self._engine = dispatcher
            self._engine.start()

    def stop(self):
        if isinstance(self._engine, AsyncServer):
            pass  # already handled by uvicorn
        else:
            self._engine: AsyncAMQPDispatcher | AsyncRedisDispatcher
            self._engine.stop()


def create_aggregator(config: dict | None = None) -> Aggregator:
    config = config or global_config
    if not config:
        raise RuntimeError(
            "Either provide a config dict or set config globally with "
            "g.set_app_config"
        )
    gaia_broker_url = config.get("GAIA_BROKER_URL", "socketio://")
    if gaia_broker_url.startswith("socketio://"):
        from src.core.communication.socketio import GaiaEventsNamespace
        return Aggregator(GaiaEventsNamespace("/gaia"))
    elif gaia_broker_url.startswith("amqp://"):
        from src.core.communication.dispatcher import GaiaEventsNamespace
        return Aggregator(GaiaEventsNamespace("gaia"))
    elif gaia_broker_url.startswith("redis://"):
        from src.core.communication.dispatcher import GaiaEventsNamespace
        return Aggregator(GaiaEventsNamespace("gaia"))
    else:
        raise RuntimeError(
            "'GAIA_BROKER_URL' is not set to a supported protocol, choose from"
            "'socketio', 'redis' or 'amqp'"
        )
