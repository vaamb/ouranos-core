#!/usr/bin/python3
from __future__ import annotations

import asyncio
import typing as t

import click

from ouranos import scheduler
from ouranos.aggregator import Aggregator
from ouranos.core.plugins import PluginManager
from ouranos.sdk import Functionality, Runner
from ouranos.web_server import WebServer


if t.TYPE_CHECKING:
    from ouranos.core.config import profile_type


@click.command(context_settings={"auto_envvar_prefix": "OURANOS"})
@click.option(
    "--config-profile",
    type=str,
    default=None,
    help="Configuration profile to use as defined in config.py.",
    show_default=True,
)
def main(
        config_profile: str | None,
):
    asyncio.run(
        run(
            config_profile,
        )
    )


async def run(
        config_profile: str | None = None,
) -> None:
    # Start the aggregator
    loop: asyncio.AbstractEventLoop = asyncio.get_event_loop()
    ouranos = Ouranos(config_profile)
    ouranos.start()
    # Run as long as requested
    runner = Runner()
    await asyncio.sleep(0.1)
    runner.add_signal_handler(loop)
    await runner.wait_forever()
    ouranos.stop()
    await runner.exit()


class Ouranos(Functionality):
    def __init__(
            self,
            config_profile: "profile_type" = None,
            config_override: dict | None = None,
    ) -> None:
        super().__init__(config_profile, config_override)
        # Init web server
        self.web_server = WebServer(self.config)
        # Init aggregator
        self.aggregator = Aggregator(self.config)
        # Init services
        """
        from ouranos.services import Services
        self.services = Services(self.config)
        """
        # Init plugins
        """
        self.plugin_manager = PluginManager()
        self.plugin_manager.register_plugins()
        """

    def _start(self):
        # Start aggregator
        self.aggregator.start()
        # Start web server
        self.web_server.start()
        # Start services
        """
        self.services.start()
        """
        # Start plugins
        """
        self.plugin_manager.start_plugins()
        """
        # Start scheduler
        self.logger.debug("Starting the Scheduler")
        scheduler.start()

    def _stop(self):
        # Stop scheduler
        self.logger.debug("Stopping the Scheduler")
        scheduler.remove_all_jobs()
        # Stop web server
        self.web_server.stop()
        # Stop aggregator
        self.aggregator.stop()


if __name__ == "__main__":
    main()
