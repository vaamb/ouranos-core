from __future__ import annotations

import asyncio
import logging
import typing as t

import click
import uvicorn

from config import default_profile, get_specified_config
import default
from src.core.g import db, set_config_globally


if t.TYPE_CHECKING:
    from dispatcher import AsyncAMQPDispatcher, AsyncRedisDispatcher
    from socketio import ASGIApp, AsyncServer

    from .dispatcher import GaiaEventsNamespace as dNamespace
    from .socketio import GaiaEventsNamespace as sNamespace


@click.option(
    "--config-profile",
    type=str,
    default=default_profile,
    help="Configuration profile to use as defined in config.py.",
    show_default=True,
)
def main(
        config_profile: str,
) -> None:
    asyncio.run(
        run(
            config_profile,
        )
    )


async def run(
        config_profile: str | None = None,
) -> None:
    # Check config
    config = get_specified_config(config_profile)
    config["START_API"] = False
    set_config_globally(config)
    # Configure logger
    from src.core.g import config
    from src.core.utils import configure_logging
    configure_logging(config)
    logger: logging.Logger = logging.getLogger(config["APP_NAME"].lower())
    # Check there is no conflict on port used
    if config.get("API_PORT") == config.get("AGGREGATOR_PORT"):
        logger.warning(
            "The Aggregator and the API are using the same port, this will "
            "lead to errors"
        )
    # Init database
    logger.info("Initializing database")
    db.init(config)
    from src.core.database.init import create_base_data
    await create_base_data(logger)
    # Start the aggregator
    loop: asyncio.AbstractEventLoop = asyncio.get_event_loop()
    logger.debug("Creating the Aggregator")
    aggregator = Aggregator(config)
    logger.info("Starting the Aggregator")
    aggregator.start()
    # Run as long as requested
    from src.core.runner import Runner
    runner = Runner()
    await asyncio.sleep(0.1)
    runner.add_signal_handler(loop)
    await runner.start()
    aggregator.stop()


class Aggregator:
    def __init__(
            self,
            config: dict | None = None,
    ) -> None:
        from src.core.g import config as global_config
        self.config = config or global_config
        if not self.config:
            raise RuntimeError(
                "Either provide a config dict or set config globally with "
                "g.set_app_config"
            )
        self._uri: str = self.config.get("GAIA_COMMUNICATION_URL")
        try:
            protocol: str = self._uri[:self._uri.index("://")]
        except ValueError:
            protocol = ""
        if protocol not in {"amqp", "redis", "socketio"}:
            raise RuntimeError(
                "'GAIA_COMMUNICATION_URL' is not set to a supported protocol, "
                "choose from 'amqp', 'redis' or 'socketio'"
            )
        if protocol == "socketio":
            from .socketio import GaiaEventsNamespace
        else:
            from .dispatcher import GaiaEventsNamespace
        self._namespace = GaiaEventsNamespace("/gaia")
        self._engine = None

    @property
    def engine(self) -> "AsyncServer" | "AsyncAMQPDispatcher" | "AsyncRedisDispatcher":
        if self._engine is None:
            raise RuntimeError
        return self._engine

    @property
    def namespace(self) -> "dNamespace" | "sNamespace":
        return self._namespace

    def start(self) -> None:
        if self._uri.startswith("socketio://"):
            host = self.config["API_HOST"]
            port = self.config["AGGREGATOR_PORT"]
            if (
                    self.config.get("START_API", default.START_API) and
                    self.config.get("API_PORT") == port
            ):
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
                    host=host, port=port,
                    server_header=False, date_header=False,
                )
                server = uvicorn.Server(config)
                asyncio.ensure_future(server.serve())
        elif self._uri.startswith("amqp://"):
            from dispatcher import AsyncAMQPDispatcher
            dispatcher = AsyncAMQPDispatcher(
                "aggregator", queue_options={"durable": True}
            )
            dispatcher.register_event_handler(self._namespace)
            self._engine = dispatcher
            self._engine.start()
        elif self._uri.startswith("redis://"):
            from dispatcher import AsyncRedisDispatcher
            dispatcher = AsyncRedisDispatcher("aggregator")
            dispatcher.register_event_handler(self._namespace)
            self._engine = dispatcher
            self._engine.start()
        else:
            raise RuntimeError

    def stop(self) -> None:
        try:
            from socketio import AsyncServer
            if isinstance(self.engine, AsyncServer):
                pass  # already handled by uvicorn
            else:
                self.engine.stop()
        except RuntimeError:
            pass  # Aggregator was not started
