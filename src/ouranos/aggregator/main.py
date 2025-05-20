from __future__ import annotations

import typing as t

import click

from dispatcher import AsyncAMQPDispatcher, AsyncRedisDispatcher

from ouranos.aggregator.archiver import Archiver
from ouranos.aggregator.events import GaiaEvents
from ouranos.aggregator.file_server import FileServer
from ouranos.aggregator.sky_watcher import SkyWatcher
from ouranos.core.dispatchers import DispatcherFactory
from ouranos.core.globals import scheduler
from ouranos.sdk import Functionality, Plugin, run_functionality_forever


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
    run_functionality_forever(Aggregator, config_profile, root=True)


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
        self._gaia_dispatcher = None
        self._internal_dispatcher = None
        self._stream_dispatcher = None
        self._event_handler = None
        self._init_gaia_events_handling()
        self.archiver = Archiver()
        self.sky_watcher = SkyWatcher()
        self.file_server = FileServer()

    @property
    def gaia_dispatcher(self) -> AsyncAMQPDispatcher | AsyncRedisDispatcher:
        if self._gaia_dispatcher is None:
            raise RuntimeError("'broker' is defined at startup")
        return self._gaia_dispatcher

    @gaia_dispatcher.setter
    def gaia_dispatcher(
            self,
            broker: AsyncAMQPDispatcher | AsyncRedisDispatcher | None
    ) -> None:
        self._gaia_dispatcher = broker

    @property
    def internal_dispatcher(self) -> AsyncAMQPDispatcher | AsyncRedisDispatcher:
        if self._internal_dispatcher is None:
            raise RuntimeError("'broker' is defined at startup")
        return self._internal_dispatcher

    @internal_dispatcher.setter
    def internal_dispatcher(
            self,
            broker: AsyncAMQPDispatcher | AsyncRedisDispatcher | None
    ) -> None:
        self._internal_dispatcher = broker

    @property
    def stream_dispatcher(self) -> AsyncAMQPDispatcher | AsyncRedisDispatcher:
        if self._stream_dispatcher is None:
            raise RuntimeError("'stream_broker' is defined at startup")
        return self._stream_dispatcher

    @stream_dispatcher.setter
    def stream_dispatcher(
            self,
            broker: AsyncAMQPDispatcher | AsyncRedisDispatcher | None
    ) -> None:
        self._stream_dispatcher = broker

    @property
    def event_handler(self) -> GaiaEvents:
        if self._event_handler is None:
            raise RuntimeError("'event_handler' is defined at startup")
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

    def _init_gaia_events_handling(self) -> None:
        # Get the dispatcher and the event handler
        self.gaia_dispatcher = DispatcherFactory.get("aggregator")
        # Create and register Gaia events handler
        self.event_handler = GaiaEvents(aggregator=self)
        self.gaia_dispatcher.register_event_handler(self.event_handler)
        # Create or get the dispatcher used for internal communication
        self.internal_dispatcher = DispatcherFactory.get("aggregator-internal")
        self.event_handler.internal_dispatcher = self.internal_dispatcher
        # Create or get the dispatcher used for short-lived messages
        self.stream_dispatcher = DispatcherFactory.get("aggregator-stream")
        self.event_handler.stream_dispatcher = self.stream_dispatcher

    async def start_gaia_events_dispatcher(self) -> None:
        await self.gaia_dispatcher.start(retry=True, block=False)
        await self.event_handler.internal_dispatcher.start(retry=True, block=False)
        await self.event_handler.stream_dispatcher.start(retry=True, block=False)
        scheduler.add_job(
            self.event_handler.log_sensors_data,
            id="log_sensors_data", trigger="cron", minute="*",
            misfire_grace_time=10
        )

    async def _startup(self) -> None:
        await self.start_gaia_events_dispatcher()
        await self.archiver.start()
        await self.sky_watcher.start()
        await self.file_server.start()

    async def _shutdown(self) -> None:
        try:
            if self.file_server.started:
                await self.file_server.stop()
            if self.sky_watcher.started:
                await self.sky_watcher.stop()
            await self.archiver.stop()
            await self.gaia_dispatcher.stop()
            await self.internal_dispatcher.stop()
            await self.stream_dispatcher.stop()
        except AttributeError:  # Not dispatcher_based
            pass  # Handled by uvicorn or by Api
        except RuntimeError:
            pass  # Aggregator was not started


aggregator_plugin = Plugin(Aggregator)
