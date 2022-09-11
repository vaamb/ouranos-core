from __future__ import annotations

import asyncio
import typing as t


if t.TYPE_CHECKING:
    from dispatcher import AsyncAMQPDispatcher, AsyncRedisDispatcher
    from socketio import ASGIApp


class Aggregator:
    def __init__(
            self,
            engine: "ASGIApp" | "AsyncAMQPDispatcher" | "AsyncRedisDispatcher"
    ):
        self._engine = engine

    @property
    def engine(self) -> "ASGIApp" | "AsyncAMQPDispatcher" | "AsyncRedisDispatcher":
        return self._engine

    def start(self, loop=None) -> None:
        if not loop:
            loop = asyncio.get_event_loop()
        if isinstance(self._engine, ASGIApp):
            import uvicorn
            uvicorn.run(self._engine, loop=loop)
        else:
            self._engine: AsyncAMQPDispatcher | AsyncRedisDispatcher
            self._engine.start(loop)


def create_aggregator(config: dict | type) -> Aggregator:
    if isinstance(config, type):
        from src.core.utils import config_dict_from_class
        config = config_dict_from_class(config)
    gaia_broker_url = config.get("GAIA_BROKER_URL", "socketio://")
    if gaia_broker_url.startswith("socketio://"):
        from socketio import ASGIApp, AsyncServer
        from src.core.communication.socketio import GaiaEventsNamespace
        sio = AsyncServer(async_mode='asgi', cors_allowed_origins=[])
        sio.register_namespace(GaiaEventsNamespace("/gaia"))
        asgi_app = ASGIApp(sio)
        return Aggregator(asgi_app)
    elif gaia_broker_url.startswith("amqp://"):
        from dispatcher import AsyncAMQPDispatcher, AsyncRedisDispatcher
        from src.core.communication.dispatcher import GaiaEventsNamespace
        dispatcher = AsyncAMQPDispatcher("aggregator")
        dispatcher.register_event_handler(GaiaEventsNamespace())
        return Aggregator(dispatcher)
    elif gaia_broker_url.startswith("redis://"):
        from dispatcher import AsyncAMQPDispatcher, AsyncRedisDispatcher
        from src.core.communication.dispatcher import GaiaEventsNamespace
        dispatcher = AsyncRedisDispatcher("aggregator")
        dispatcher.register_event_handler(GaiaEventsNamespace())
        return Aggregator(dispatcher)
    else:
        """logger.warning(
            "'GAIA_BROKER_URL' is not set to a supported protocol, choose from"
            "'socketio', 'redis' or 'amqp'"
        )"""
