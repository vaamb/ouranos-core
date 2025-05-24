from __future__ import annotations

from typing import Any

from click import Command, Context, MultiCommand

from ouranos.core.config import ConfigHelper
from ouranos.core.plugins_manager import PluginManager


class RootCommand(MultiCommand):
    def _get_config_profile(self, ctx: Context) -> Any:
        default_profile = None
        for param in self.params:
            if param.human_readable_name == "config_profile":
                default_profile = param.default
                break
        return ctx.params.get("config_profile", default_profile)

    def get_command(self, ctx: Context, cmd_name: str) -> Command | None:
        if not ConfigHelper.config_is_set():
            # When using "--help" flag, click will loop through all the commands
            #  found via `list_commands` and use `get_command` on each of them
            #  to get the info needed.
            config_profile = self._get_config_profile(ctx)
            ConfigHelper.set_config_and_configure_logging(config_profile)
        pm: PluginManager = PluginManager()
        pm.register_plugins()
        plugin = pm.plugins.get(cmd_name)
        if plugin is None:
            return None
        return plugin.command

    def list_commands(self, ctx: Context) -> list[str]:
        config_profile = self._get_config_profile(ctx)
        ConfigHelper.set_config_and_configure_logging(config_profile)
        pm: PluginManager = PluginManager()
        pm.register_plugins()
        return [plugin_name for plugin_name in pm.plugins.keys()]
