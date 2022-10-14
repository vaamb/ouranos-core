from __future__ import annotations

import asyncio
import typing as t

import uvicorn

import default
from src.core.g import config as global_config


if t.TYPE_CHECKING:
    from dispatcher import AsyncAMQPDispatcher, AsyncRedisDispatcher
    from socketio import ASGIApp, AsyncServer

    from .dispatcher import GaiaEventsNamespace as dNamespace
    from .socketio import GaiaEventsNamespace as sNamespace


class Aggregator:
    def __init__(
            self,
            namespace: "dNamespace" | "sNamespace",
            config: dict | None = None,
            gaia_communication_url: str | None = None
    ):
        self.config = config or global_config
        if not self.config:
            raise RuntimeError(
                "Either provide a config dict or set config globally with "
                "g.set_app_config"
            )
        self._namespace: "dNamespace" | "sNamespace" = namespace
        self._engine = None
        self._url: str = gaia_communication_url or self.config.get(
            "GAIA_COMMUNICATION_URL", default.GAIA_COMMUNICATION_URL
        )
        protocol = self._url[:self._url.index("://")]
        if protocol not in {"amqp", "redis", "socketio"}:
            raise ValueError(
                f"The protocol {protocol} is not supported to communicate with "
                f"Gaia, please choose from `amqp`, `redis` or `socketio` and "
                f"set `GAIA_COMMUNICATION_URL` to the chosen value"
            )

    @property
    def engine(self) -> "ASGIApp" | "AsyncAMQPDispatcher" | "AsyncRedisDispatcher":
        if self._engine is None:
            raise RuntimeError
        return self._engine

    @property
    def namespace(self) -> "dNamespace" | "sNamespace":
        return self._namespace

    def start(self) -> None:
        if self._url.startswith("socketio://"):
            if self.config.get("START_API", default.START_API):
                from src.app import sio
                sio.register_namespace(self._namespace)
                self._engine = sio
            else:
                from socketio import ASGIApp, AsyncServer
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
        elif self._url.startswith("amqp://"):
            from dispatcher import AsyncAMQPDispatcher
            dispatcher = AsyncAMQPDispatcher(
                "aggregator", queue_options={"durable": True}
            )
            dispatcher.register_event_handler(self._namespace)
            self._engine = dispatcher
            self._engine.start()
        elif self._url.startswith("redis://"):
            from dispatcher import AsyncRedisDispatcher
            dispatcher = AsyncRedisDispatcher("aggregator")
            dispatcher.register_event_handler(self._namespace)
            self._engine = dispatcher
            self._engine.start()
        else:
            raise RuntimeError

    def stop(self):
        from socketio import AsyncServer
        if isinstance(self._engine, AsyncServer):
            pass  # already handled by uvicorn
        else:
            self._engine: "AsyncAMQPDispatcher" | "AsyncRedisDispatcher"
            self._engine.stop()


def create_aggregator(config: dict | None = None) -> Aggregator:
    config = config or global_config
    if not config:
        raise RuntimeError(
            "Either provide a config dict or set config globally with "
            "g.set_app_config"
        )
    gaia_communication_url = config.get("GAIA_COMMUNICATION_URL")
    if gaia_communication_url.startswith("socketio://"):
        from .socketio import GaiaEventsNamespace
    elif gaia_communication_url.startswith("amqp://"):
        from .dispatcher import GaiaEventsNamespace
    elif gaia_communication_url.startswith("redis://"):
        from .dispatcher import GaiaEventsNamespace
    else:
        raise RuntimeError(
            "'GAIA_COMMUNICATION_URL' is not set to a supported protocol, choose from"
            "'socketio', 'redis' or 'amqp'"
        )
    return Aggregator(GaiaEventsNamespace("/gaia"))
