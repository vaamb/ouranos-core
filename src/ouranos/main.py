#!/usr/bin/python3
from __future__ import annotations

import typing as t

import click

from ouranos import scheduler
from ouranos.aggregator import Aggregator
from ouranos.core.cli import RootCommand
from ouranos.core.plugins import PluginManager
from ouranos.sdk import Functionality, Plugin, run_functionality_forever
from ouranos.web_server import WebServer


if t.TYPE_CHECKING:
    from ouranos.core.config import profile_type


@click.command(
    cls=RootCommand,
    invoke_without_command=True,
    context_settings={"auto_envvar_prefix": "OURANOS"}
)
@click.option(
    "--config-profile",
    type=str,
    default=None,
    help="Configuration profile to use as defined in config.py.",
    show_default=True,
)
@click.pass_context
def main(
        ctx: click.Context,
        config_profile: str | None,
):
    """Launch Ouranos

    Launch all the functionalities linked to Ouranos as a single monolithic
    process
    """
    if ctx.invoked_subcommand is None:
        run_functionality_forever(Ouranos, config_profile)


class Ouranos(Functionality):
    def __init__(
            self,
            config_profile: "profile_type" = None,
            config_override: dict | None = None,
    ) -> None:
        super().__init__(config_profile, config_override, root=True)
        self._plugins: dict[str, Plugin] = {}
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
        self.plugin_manager = PluginManager()
        # TODO: inject router
        # self.plugin_manager.register_new_functionalities()
        self.plugin_manager.register_plugins()
        self.plugin_manager.init_plugins()

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
        self.plugin_manager.start_plugins()
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
