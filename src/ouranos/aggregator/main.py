from __future__ import annotations

import asyncio
import typing as t

import click
import uvicorn

from ouranos.aggregator.archiver import Archiver
from ouranos.aggregator.sky_watcher import SkyWatcher
from ouranos.core.utils import InternalEventsDispatcherFactory
from ouranos.sdk import Functionality, run_functionality_forever


if t.TYPE_CHECKING:
    from dispatcher import AsyncAMQPDispatcher, AsyncRedisDispatcher
    from socketio import ASGIApp, AsyncServer

    from ouranos.aggregator.events import (
        DispatcherBasedGaiaEvents, SioBasedGaiaEvents
    )
    from ouranos.core.config import profile_type


@click.command()
@click.option(
    "--config-profile",
    type=str,
    default=None,
    help="Configuration profile to use as defined in config.py.",
    show_default=True,
)
def main(
        config_profile: str | None,
) -> None:
    """Launch Ouranos'Aggregator

    The Aggregator is the main data entry point from Gaia's instances. It
    receives all the environmental data and logs in into a database that can be
    searched by other functionalities
    """
    run_functionality_forever(Aggregator, config_profile)


class Aggregator(Functionality):
    def __init__(
            self,
            config_profile: "profile_type" = None,
            config_override: dict | None = None,
            **kwargs
    ) -> None:
        """The Gaia data aggregator.
        This functionality collects data from, and sends instructions to Gaia
        instances. It can work using a message queue such as RabbitMQ (the
        recommended way) via a custom events dispatcher, or using socketio via
        `python-socketio`.

        :param config_profile: The configuration profile to provide. Either a
        `BaseConfig` or its subclass, a str corresponding to a profile name
        accessible in a `config.py` file, or None to take the default profile.
        :param config_override: A dictionary containing some overriding
        parameters for the configuration.
        :param kwargs: Other parameters to pass to the base class.
        """
        super().__init__(config_profile, config_override, **kwargs)
        self.gaia_broker_uri: str = self.config["GAIA_COMMUNICATION_URL"]
        if (
            self.gaia_broker_uri.startswith("socketio://") and
            self.config["API_PORT"] == self.config["AGGREGATOR_PORT"]
        ):
            self.logger.warning(
                "The Aggregator and the API are using the same port, this will "
                "lead to errors"
            )

        try:
            protocol: str = self.gaia_broker_uri[:self.gaia_broker_uri.index("://")]
        except ValueError:
            protocol = ""
        if protocol not in {"amqp", "redis", "socketio"}:
            raise RuntimeError(
                "'GAIA_COMMUNICATION_URL' is not set to a supported protocol, "
                "choose from 'amqp://', 'redis://' or 'socketio://'"
            )
        self._engine = None
        self._event_handler = None
        self.archiver = Archiver()
        self.sky_watcher = SkyWatcher()

    @property
    def engine(self) -> "AsyncServer" | "AsyncAMQPDispatcher" | "AsyncRedisDispatcher":
        if self._engine is None:
            raise RuntimeError("engine is defined at startup")
        return self._engine

    @engine.setter
    def engine(self, engine: "AsyncServer" | "AsyncAMQPDispatcher" | "AsyncRedisDispatcher"):
        self._engine = engine

    @property
    def event_handler(self) -> "DispatcherBasedGaiaEvents" | "SioBasedGaiaEvents":
        if self._event_handler is None:
            raise RuntimeError("No event handler defined")
        return self._event_handler

    @event_handler.setter
    def event_handler(self, event_handler: "DispatcherBasedGaiaEvents" | "SioBasedGaiaEvents"):
        self._event_handler = event_handler

    def _startup(self) -> None:
        if self.gaia_broker_uri.startswith("socketio://"):
            self.logger.debug(
                "Using Socket.IO as the message broker with Gaia"
            )
            # Get the event handler
            from ouranos.aggregator.events import SioBasedGaiaEvents
            self.event_handler = SioBasedGaiaEvents()
            # Create the dispatcher used for internal communication and use it
            #  in the event handler
            ouranos_dispatcher = InternalEventsDispatcherFactory.get("aggregator")
            self.event_handler.ouranos_dispatcher = ouranos_dispatcher
            # Create the sio server used to communicate with Gaia
            #  It might be the same as the one used for webserver
            host = self.config["API_HOST"]
            port = self.config["AGGREGATOR_PORT"]
            if (
                    self.config["START_API"] and
                    self.config["API_PORT"] == port
            ):
                from ouranos.web_server.factory import sio
                self.engine = sio
                self.engine.register_namespace(self.event_handler)
            else:
                from socketio import ASGIApp, AsyncServer
                self.engine = AsyncServer(async_mode='asgi', cors_allowed_origins=[])
                self.engine.register_namespace(self.event_handler)
                asgi_app = ASGIApp(self.engine)
                config = uvicorn.Config(
                    asgi_app,
                    host=host, port=port,
                    log_config=None, server_header=False, date_header=False,
                )
                server = uvicorn.Server(config)
                asyncio.ensure_future(server.serve())
        elif self.gaia_broker_uri.startswith("amqp://") or self.gaia_broker_uri.startswith("redis://"):
            # Get the event handler
            from ouranos.aggregator.events import DispatcherBasedGaiaEvents
            self.event_handler = DispatcherBasedGaiaEvents()
            # Create the dispatcher used to communicate with gaia
            if self.gaia_broker_uri.startswith("amqp://"):
                self.logger.debug(
                    "Using RabbitMQ as the message broker with Gaia")
                if self.gaia_broker_uri == "amqp://":
                    # replace with default url
                    broker_uri = "amqp://guest:guest@localhost:5672//"
                else:
                    broker_uri = self.gaia_broker_uri
                from dispatcher import AsyncAMQPDispatcher as Dispatcher
            else:
                self.logger.debug(
                    "Using Redis as the message broker with Gaia")
                if self.gaia_broker_uri == "redis://":
                    # replace with default url
                    broker_uri = "redis://localhost:6379/0"
                else:
                    broker_uri = self.gaia_broker_uri
                from dispatcher import AsyncRedisDispatcher as Dispatcher
            self.engine = Dispatcher(
                "aggregator", url=broker_uri, queue_options={"durable": True})
            # Create the dispatcher used for internal communication
            #  It might be the same as the one used to communicate with Gaia
            separate_ouranos_dispatcher: bool
            if self.config["DISPATCHER_URL"] == self.gaia_broker_uri:
                self.event_handler.ouranos_dispatcher = self.engine
                separate_ouranos_dispatcher = False
            else:
                self.event_handler.ouranos_dispatcher = InternalEventsDispatcherFactory.get("aggregator")
                separate_ouranos_dispatcher = True
            # Use the internal dispatcher in the event dispatcher
            self.engine.register_event_handler(self.event_handler)
            self.engine.start(retry=True, block=False)
            if separate_ouranos_dispatcher:
                self.event_handler.ouranos_dispatcher.start(retry=True, block=False)
        else:
            raise RuntimeError
        self.archiver.start()
        self.sky_watcher.start()

    def _shutdown(self) -> None:
        try:
            self.sky_watcher.stop()
            self.archiver.stop()
            self.engine.stop()
        except AttributeError:  # Not dispatcher_based
            pass  # Handled by uvicorn or by Api
        except RuntimeError:
            pass  # Aggregator was not started
