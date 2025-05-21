#!/usr/bin/python3
from __future__ import annotations

import typing as t

import click

from ouranos.cli import RootCommand
from ouranos.core.plugins_manager import PluginManager
from ouranos.sdk import BaseFunctionality

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
@click.option(
    "--use-multiprocess",
    type=bool,
    default=False,
    help="Launch compatible functionalities as separate processes.",
    show_default=True,
)
@click.pass_context
def main(
        ctx: click.Context,
        config_profile: str | None,
        use_multiprocess: bool,
):
    """Launch Ouranos

    Launch all the functionalities linked to Ouranos as a single monolithic
    process
    """
    if ctx.invoked_subcommand is None:
        ouranos = Ouranos(config_profile, use_multiprocess=use_multiprocess)
        ouranos.run()


class Ouranos(BaseFunctionality):
    _is_microservice = False

    def __init__(
            self,
            config_profile: "profile_type" = None,
            config_override: dict | None = None,
            **kwargs,
    ) -> None:
        """The master functionality.
        This functionality is able to launch all the other functionalities,
        either core functionalities (the Webserver, the Aggregator) or plugins.

        :param config_profile: The configuration profile to provide. Either a
        `BaseConfig` or its subclass, a str corresponding to a profile name
        accessible in a `config.py` file, or None to take the default profile.
        :param config_override: A dictionary containing some overriding
        parameters for the configuration.
        :param kwargs: Other parameters to pass to the base class.
        """
        super().__init__(config_profile, config_override, root=True, **kwargs)
        self.plugin_manager = PluginManager()
        # Register all the plugins at the beginning as it allows to load all the
        #  models needed
        self.plugin_manager.register_plugins()

    async def _startup(self) -> None:
        for plugin in self.plugin_manager.plugins.values():
            kwargs = plugin.kwargs
            kwargs["root"] = False
            kwargs["microservice"] = False
            plugin.kwargs = kwargs
            await plugin.start()

    async def _shutdown(self) -> None:
        for plugin in self.plugin_manager.plugins.values():
            await plugin.stop()


if __name__ == "__main__":
    main()
