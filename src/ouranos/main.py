#!/usr/bin/python3
from __future__ import annotations

import asyncio
from logging import getLogger, Logger
import os

import click

from ouranos.cli import RootCommand
from ouranos.core.config import ConfigDict, ConfigHelper
from ouranos.core.plugins_manager import PluginManager
from ouranos.core.utils import parse_str_value
from ouranos.sdk import Functionality


@click.command(
    cls=RootCommand,
    invoke_without_command=True,
    context_settings={"auto_envvar_prefix": "OURANOS"}
)
@click.option(
    "--config-profile", "-c",
    type=str,
    default=None,
    help="Configuration profile to use as defined in config.py.",
    show_default=True,
)
@click.option(
    "--config-override", "-co",
    type=str,
    multiple=True,
    default=None,
    help="Config parameters to override written as key=value.",
    show_default=True,
)
@click.pass_context
def main(
        ctx: click.Context,
        config_profile: str | None,
        config_override: list[str],
):
    """Launch Ouranos

    Launch all the functionalities linked to Ouranos as a single monolithic
    process
    """
    config_override_str = config_override
    config_override = {}
    for overridden in config_override_str:
        key, value = overridden.split("=")
        config_override[key] = parse_str_value(value)

    if ctx.invoked_subcommand is None:
        config = ConfigHelper.set_config(config_profile)
        config.update(config_override)
        ConfigHelper._config = None
        ConfigHelper.set_config_and_configure_logging(config)
        ouranos = Ouranos(config)
        ouranos.run()


class Ouranos(Functionality):
    _is_microservice = False

    def __init__(
            self,
            config: ConfigDict,
            **kwargs,
    ) -> None:
        """The master functionality.
        This functionality is able to launch all the other functionalities,
        either core functionalities (the Webserver, the Aggregator) or plugins.

        :param config: The configuration to provide as a `BaseConfigDict`.
        """
        super().__init__(config, **kwargs)
        self.logger: Logger = getLogger(f"ouranos")
        self.plugin_manager = PluginManager()
        # Register all the plugins at the beginning as it allows to load all the
        #  models needed
        self.plugin_manager.register_plugins()

    async def _startup(self) -> None:
        for plugin in self.plugin_manager.plugins.values():
            plugin.setup_config(self.config)
            plugin.kwargs = {
                "root": False,
                "microservice": False,
            }
            await plugin.start()

    async def _shutdown(self) -> None:
        for plugin in self.plugin_manager.plugins.values():
            await plugin.stop()

    async def startup(self) -> None:
        if self._status:
            raise RuntimeError("Ouranos has already started")
        pid = os.getpid()
        self.logger.info(f"Starting Ouranos [{pid}]")
        try:
            await self._init_common()
            await self.initialize()
            await self._startup()
        except Exception as e:
            self.logger.error(
                f"Error while starting [{pid}]. Error msg: {self._fmt_exc(e)}")
        else:
            self.logger.info(f"Ouranos has been started [{pid}]")
            self._status = True

    async def shutdown(self) -> None:
        if not self._status:
            raise RuntimeError("Ouranos is not running")
        # Stop the functionality
        pid = os.getpid()
        self.logger.info(f"Stopping Ouranos [{pid}]")
        try:
            await self._shutdown()
            await self.post_shutdown()
        except asyncio.CancelledError as e:
            self.logger.error(
                f"Error while shutting down. Error msg: {self._fmt_exc(e)}")
        else:
            self._status = False
            self.logger.info(f"Ouranos has been stopped [{pid}]")


if __name__ == "__main__":
    main()
