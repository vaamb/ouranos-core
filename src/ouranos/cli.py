from __future__ import annotations

from typing import Any
import warnings

from click import Command, Context, Group

from ouranos.core.config import ConfigHelper
from ouranos.core.plugins_manager import PluginManager


class RootCommand(Group):
    def _get_config_profile(self, ctx: Context) -> Any:
        default_profile = None
        for param in self.params:
            if param.human_readable_name == "config_profile":
                default_profile = param.default
                break
        return ctx.params.get("config_profile", default_profile)

    def _set_config(self, ctx: Context) -> None:
        if not ConfigHelper.config_is_set():
            config_profile = self._get_config_profile(ctx)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                ConfigHelper.set_config_and_configure_logging(config_profile)

    def get_command(self, ctx: Context, cmd_name: str) -> Command | None:
        # If the command is a registered command, return it
        if cmd_name in self.commands:
            return self.commands[cmd_name]

        # If the command is a plugin command, return it
        self._set_config(ctx)
        pm: PluginManager = PluginManager()
        if not pm.plugins:
            pm.register_plugins(omit_excluded=False)  # Allow to launch an omitted plugin
        if cmd_name in pm.plugins:
            return pm.plugins[cmd_name].command

        # If the command is not found, return None
        return None

    def list_commands(self, ctx: Context) -> list[str]:
        self._set_config(ctx)
        pm: PluginManager = PluginManager()
        pm.register_plugins(omit_excluded=False)  # List all plugins installed
        return sorted(pm.plugins) + sorted(self.commands)
