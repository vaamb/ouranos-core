from __future__ import annotations

import asyncio
import logging
import typing as t

import click
import uvicorn

from config import default_profile, get_specified_config
import default
from src.core.g import db, set_config_globally
from src.core.utils import DispatcherFactory


if t.TYPE_CHECKING:
    from dispatcher import AsyncAMQPDispatcher, AsyncRedisDispatcher
    from socketio import ASGIApp, AsyncServer

    from aggregator.dispatcher_communication import GaiaEventsNamespace as dNamespace
    from aggregator.socketio_communication import GaiaEventsNamespace as sNamespace


@click.command()
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
    app_name = config["APP_NAME"].lower()
    from setproctitle import setproctitle
    setproctitle(f"{app_name}-aggregator")
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
    from src.core.database import models  # noqa
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
    await runner.wait_forever()
    aggregator.stop()
    await runner.exit()


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
            from aggregator.socketio_communication import GaiaEventsNamespace
        else:
            from aggregator.dispatcher_communication import GaiaEventsNamespace
        self._namespace = GaiaEventsNamespace("/gaia")
        self._engine = None
        # TODO: add a dispatcher, can be same as engine if same url, to dispatch
        #  events locally

    @property
    def engine(self) -> "AsyncServer" | "AsyncAMQPDispatcher" | "AsyncRedisDispatcher":
        if self._engine is None:
            raise RuntimeError("engine is defined at startup")
        return self._engine

    @property
    def namespace(self) -> "dNamespace" | "sNamespace":
        return self._namespace

    def start(self) -> None:
        if self._uri.startswith("socketio://"):
            # Create the dispatcher
            dispatcher = DispatcherFactory.get("aggregator")
            self._namespace.dispatcher = dispatcher
            # Create the communication mean with Gaia
            host = self.config["API_HOST"]
            port = self.config["AGGREGATOR_PORT"]
            if (
                    self.config.get("START_API", default.START_API) and
                    self.config.get("API_PORT") == port
            ):
                from src.app.factory import sio
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
            communication_mean = AsyncAMQPDispatcher(
                "aggregator", queue_options={"durable": True}
            )
            if self.config.get("DISPATCHER_URL") == self._uri:
                dispatcher = communication_mean
            else:
                dispatcher = DispatcherFactory.get("aggregator")
            self._namespace.dispatcher = dispatcher
            communication_mean.register_event_handler(self._namespace)
            self._engine = communication_mean
            self._engine.start()
        elif self._uri.startswith("redis://"):
            from dispatcher import AsyncRedisDispatcher
            communication_mean = AsyncRedisDispatcher("aggregator")
            if self.config.get("DISPATCHER_URL") == self._uri:
                dispatcher = communication_mean
            else:
                dispatcher = DispatcherFactory.get("aggregator")
            self._namespace.dispatcher = dispatcher
            communication_mean.register_event_handler(self._namespace)
            self._engine = communication_mean
            self._engine.start()
        else:
            raise RuntimeError

    def stop(self) -> None:
        try:
            self.engine.stop()
        except AttributeError:  # Not dispatcher_based
            pass  # Handled by uvicorn or by App
        except RuntimeError:
            pass  # Aggregator was not started


if __name__ == "__main__":
    main()
