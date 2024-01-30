from __future__ import annotations

from typing import Any

from click import Command, Context, MultiCommand

from ouranos.aggregator.main import main as aggregator
from ouranos.core.config import ConfigHelper
from ouranos.core.plugins_manager import PluginManager
from ouranos.web_server.main import main as webserver


class RootCommand(MultiCommand):
    _builtin_commands = {
        "aggregator": aggregator,
        "server": webserver
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._plugin_commands: dict[str, Command] = {}

    def _get_config_profile(self, ctx: Context) -> Any:
        default_profile = None
        for param in self.params:
            if param.human_readable_name == "config_profile":
                default_profile = param.default
                break
        return ctx.params.get("config_profile", default_profile)

    @property
    def plugin_commands(self) -> dict[str, Command]:
        if not ConfigHelper.config_is_set():
            raise RuntimeError("Config should be set to use this method.")
        if not self._plugin_commands:
            pm: PluginManager = PluginManager()
            pm.register_plugins()
            for plugin_name, plugin in pm.plugins.items():
                self._plugin_commands[plugin_name] = plugin.command
        return self._plugin_commands

    def get_command(self, ctx: Context, cmd_name: str) -> Command | None:
        if not ConfigHelper.config_is_set():
            # When using "--help" flag, click will loop through all the commands
            #  found via `list_commands` and use `get_command` on each of them
            #  to get the info needed.
            config_profile = self._get_config_profile(ctx)
            ConfigHelper.set_config_and_configure_logging(config_profile)
        if cmd_name in self._builtin_commands:
            return self._builtin_commands[cmd_name]
        return self.plugin_commands.get(cmd_name)

    def list_commands(self, ctx: Context) -> list[str]:
        config_profile = self._get_config_profile(ctx)
        ConfigHelper.set_config_and_configure_logging(config_profile)
        plugin_commands_list = [cmd for cmd in self.plugin_commands]
        plugin_commands_list.sort()
        return [cmd for cmd in self._builtin_commands] + plugin_commands_list
