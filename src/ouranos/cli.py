from __future__ import annotations

from click import Command, Context, MultiCommand

from ouranos.aggregator.main import main as aggregator
from ouranos.core.plugins import PluginManager
from ouranos.web_server.main import main as webserver


class RootCommand(MultiCommand):
    _builtin_commands = {
        "aggregator": aggregator,
        "server": webserver
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._plugin_commands: dict[str, Command] = {}
        # TODO: register plugins

    @property
    def plugin_commands(self) -> dict[str, Command]:
        if not self._plugin_commands:
            pm: PluginManager = PluginManager()
            pm.register_plugins()
            for plugin_name, plugin in pm.plugins.items():
                self._plugin_commands[plugin_name] = plugin.command
        return self._plugin_commands

    def get_command(self, ctx: Context, cmd_name: str) -> Command | None:
        if cmd_name in self._builtin_commands:
            return self._builtin_commands[cmd_name]
        return self.plugin_commands.get(cmd_name)

    def list_commands(self, ctx):
        plugin_commands_list = [cmd for cmd in self.plugin_commands]
        plugin_commands_list.sort()
        return [cmd for cmd in self._builtin_commands] + plugin_commands_list
