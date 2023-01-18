from __future__ import annotations

from click import Command, Context, echo, MultiCommand

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
        self.pm: PluginManager = PluginManager()
        # TODO: register plugins

    def get_command(self, ctx: Context, cmd_name: str) -> Command | None:
        if cmd_name in self._builtin_commands:
            return self._builtin_commands[cmd_name]
        try:
            plugin = self.pm.plugins[cmd_name]
        except KeyError:
            echo(f"Error: Ouranos has no command named {cmd_name}")
            ctx.exit(2)
        else:
            return plugin.command

    def list_commands(self, ctx):
        return [cmd for cmd in self._builtin_commands]
