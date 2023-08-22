from __future__ import annotations

import typing as t

import click

from dispatcher import (
    AsyncAMQPDispatcher, AsyncEventHandler, AsyncRedisDispatcher, Dispatcher)

from ouranos.aggregator.archiver import Archiver
from ouranos.aggregator.events import GaiaEvents
from ouranos.aggregator.sky_watcher import SkyWatcher
from ouranos.core.utils import InternalEventsDispatcherFactory
from ouranos.sdk import Functionality, run_functionality_forever


if t.TYPE_CHECKING:
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
        instances. It works using a message queue such as RabbitMQ (the
        recommended way) via a custom events' dispatcher.

        :param config_profile: The configuration profile to provide. Either a
        `BaseConfig` or its subclass, a str corresponding to a profile name
        accessible in a `config.py` file, or None to take the default profile.
        :param config_override: A dictionary containing some overriding
        parameters for the configuration.
        :param kwargs: Other parameters to pass to the base class.
        """
        super().__init__(config_profile, config_override, **kwargs)
        gaia_broker_uri: str = self.config["GAIA_COMMUNICATION_URL"]
        if not self._check_broker_protocol(gaia_broker_uri, {"amqp", "redis"}):
            raise ValueError(
                "'GAIA_COMMUNICATION_URL' is not set to a supported protocol, "
                "choose from 'amqp://' or 'redis://'")
        self._broker = None
        self._event_handler = None
        self.archiver = Archiver()
        self.sky_watcher = SkyWatcher()

    @property
    def broker(self) -> AsyncAMQPDispatcher | AsyncRedisDispatcher:
        if self._broker is None:
            raise RuntimeError("engine is defined at startup")
        return self._broker

    @broker.setter
    def broker(
            self,
            engine: AsyncAMQPDispatcher | AsyncRedisDispatcher | None
    ) -> None:
        self._broker = engine

    @property
    def event_handler(self) -> GaiaEvents:
        if self._event_handler is None:
            raise RuntimeError("No event handler defined")
        return self._event_handler

    @event_handler.setter
    def event_handler(
            self,
            event_handler: GaiaEvents | None
    ) -> None:
        self._event_handler = event_handler

    @staticmethod
    def _check_broker_protocol(broker_uri: str, choices: set) -> bool:
        protocol: str | None
        try:
            protocol = broker_uri[:broker_uri.index("://")]
        except ValueError:
            protocol = None
        if protocol in choices:
            return True
        return False

    def create_handler(
            self,
            broker_uri: str,
            broker_options: dict | None = None,
    ) -> tuple[Dispatcher, AsyncEventHandler]:
        broker_options = broker_options or {}
        # Get the event handler
        dispatcher = GaiaEvents()
        # Create the broker used to communicate with gaia
        if broker_uri.startswith("amqp://"):
            self.logger.debug(
                "Using RabbitMQ as the message broker with Gaia")
            if broker_uri == "amqp://":
                # Use default rabbitmq uri
                broker_uri = "amqp://guest:guest@localhost:5672//"
            from dispatcher import AsyncAMQPDispatcher
            broker = AsyncAMQPDispatcher(
                "aggregator", url=broker_uri, **broker_options)
        else:
            self.logger.debug(
                "Using Redis as the message broker with Gaia")
            if broker_uri == "redis://":
                # Use default Redis uri
                broker_uri = "redis://localhost:6379/0"
            from dispatcher import AsyncRedisDispatcher
            broker = AsyncRedisDispatcher(
                "aggregator", url=broker_uri)
        return broker, dispatcher

    def _startup_gaia_communications(self) -> None:
        # Get the dispatcher and the event handler
        self.broker, self.event_handler = self.create_handler(
            broker_uri=self.config["GAIA_COMMUNICATION_URL"],
            broker_options={
                "queue_options": {
                    "arguments": {
                        # Remove queue after 1 day without consumer
                        "x-expires": 60 * 60 * 24 * 1000,
                    },
                },
            },
        )
        # Create or get the dispatcher used for internal communication
        #  Rem: it might be the same as the one used to communicate with Gaia
        separate_ouranos_dispatcher: bool
        if self.config["DISPATCHER_URL"] == self.config["GAIA_COMMUNICATION_URL"]:
            self.event_handler.ouranos_dispatcher = self.broker
            separate_ouranos_dispatcher = False
        else:
            self.event_handler.ouranos_dispatcher = \
                InternalEventsDispatcherFactory.get("aggregator")
            separate_ouranos_dispatcher = True
        # Use the internal dispatcher in the event dispatcher
        self.broker.register_event_handler(self.event_handler)
        self.broker.start(retry=True, block=False)
        if separate_ouranos_dispatcher:
            self.event_handler.ouranos_dispatcher.start(retry=True, block=False)

    def _startup(self) -> None:
        self._startup_gaia_communications()
        self.archiver.start()
        self.sky_watcher.start()

    def _shutdown(self) -> None:
        try:
            self.sky_watcher.stop()
            self.archiver.stop()
            self.broker.stop()
        except AttributeError:  # Not dispatcher_based
            pass  # Handled by uvicorn or by Api
        except RuntimeError:
            pass  # Aggregator was not started
