#!/usr/bin/python3
from __future__ import annotations

import asyncio
from logging import getLogger
from typing import Any
import warnings

import click

from ouranos.cli import RootCommand
from ouranos.core.config import ConfigDict, ConfigHelper
from ouranos.core.database.init import check_db_revision, create_db_tables
from ouranos.core.globals import db
from ouranos.core.plugins_manager import PluginManager
from ouranos.core.utils import parse_str_value
from ouranos.sdk import Host, Plugin


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
    config_override_dict: dict[str, Any] = {}
    for overridden in config_override:
        key, value = overridden.split("=")
        config_override_dict[key] = parse_str_value(value)

    if ctx.invoked_subcommand is None:
        config = ConfigHelper.set_config_and_configure_logging(
            config_profile, config_override_dict)
        ouranos = Ouranos(config)
        ouranos.run()


class Ouranos(Host):
    def __init__(self, config: ConfigDict) -> None:
        """The master host.

        This host runs every registered plugin, core ones (the Aggregator, the
        Webserver) included, in a single monolithic process (plus the
        plugins' workers).

        :param config: The configuration to provide as a `BaseConfigDict`.
        """
        plugin_manager = PluginManager()
        # Register all the plugins at the beginning as it allows to load all the
        #  models needed
        if not plugin_manager.plugins_are_registered:
            plugin_manager.register_plugins()

        plugins: list[Plugin] = []
        for plugin in plugin_manager.plugins.values():
            # Routes-only extensions have no functionality to run
            if not isinstance(plugin, Plugin):
                continue
            plugin.setup_config(config)
            plugin.update_kwargs({"root": False, "microservice": False})
            plugins.append(plugin)

        super().__init__("ouranos", config, plugins)


async def _fill_db(check_revision: bool = True):
    if not ConfigHelper.config_is_set():
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            ConfigHelper.set_config_and_configure_logging(None)
    config = ConfigHelper.get_config()
    db.init(config)  # ty: ignore[invalid-argument-type]  # TypedDict vs dict
    if check_revision:
        await check_db_revision()
    await create_db_tables()


@main.command()
@click.option(
    "--check-revision/--no-check-revision",
    type=bool,
    default=True,
    help="Check if the database revision is up to date.",
    show_default=True,
    is_flag=True,
)
def fill_db(check_revision: bool = True):
    """Fill the database with the default tables."""
    asyncio.run(_fill_db(check_revision=check_revision))


if __name__ == "__main__":
    main()
