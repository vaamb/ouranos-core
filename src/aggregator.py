from __future__ import annotations

import asyncio

from dispatcher import AsyncAMQPDispatcher, AsyncRedisDispatcher
from socketio import ASGIApp

from src.core.g import config as global_config


class Aggregator:
    def __init__(
            self,
            engine: ASGIApp | AsyncAMQPDispatcher | AsyncRedisDispatcher
    ):
        self._engine = engine

    @property
    def engine(self) -> ASGIApp | AsyncAMQPDispatcher | AsyncRedisDispatcher:
        return self._engine

    def start(self, loop=None) -> None:
        if not loop:
            loop = asyncio.get_event_loop()
        if isinstance(self._engine, ASGIApp):
            self._engine: ASGIApp
            import uvicorn
            config = uvicorn.Config(
                self._engine,
                port=5000,
                loop=loop,
                server_header=False, date_header=False,
            )
            server = uvicorn.Server(config)
            loop.create_task(server.serve())
        else:
            self._engine: AsyncAMQPDispatcher | AsyncRedisDispatcher
            self._engine.start(loop)


def create_aggregator(config: dict | None = None) -> Aggregator:
    config = config or global_config
    if not config:
        raise RuntimeError(
            "Either provide a config dict or set config globally with "
            "g.set_app_config"
        )
    gaia_broker_url = config.get("GAIA_BROKER_URL", "socketio://")
    if gaia_broker_url.startswith("socketio://"):
        from socketio import ASGIApp, AsyncServer
        from src.core.communication.socketio import GaiaEventsNamespace
        sio = AsyncServer(async_mode='asgi', cors_allowed_origins=[])
        sio.register_namespace(GaiaEventsNamespace("/gaia"))
        asgi_app = ASGIApp(sio)
        return Aggregator(asgi_app)
    elif gaia_broker_url.startswith("amqp://"):
        from dispatcher import AsyncAMQPDispatcher
        from src.core.communication.dispatcher import GaiaEventsNamespace
        dispatcher = AsyncAMQPDispatcher("aggregator")
        dispatcher.register_event_handler(GaiaEventsNamespace())
        return Aggregator(dispatcher)
    elif gaia_broker_url.startswith("redis://"):
        from dispatcher import AsyncRedisDispatcher
        from src.core.communication.dispatcher import GaiaEventsNamespace
        dispatcher = AsyncRedisDispatcher("aggregator")
        dispatcher.register_event_handler(GaiaEventsNamespace())
        return Aggregator(dispatcher)
    else:
        raise RuntimeError(
            "'GAIA_BROKER_URL' is not set to a supported protocol, choose from"
            "'socketio', 'redis' or 'amqp'"
        )
