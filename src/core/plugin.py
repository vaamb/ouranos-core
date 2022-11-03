import importlib
from importlib_metadata import entry_points

from click import Command, Group


class Plugin:
    def __init__(self, name: str, main: Command):
        self.name = name
        self.main = main

    def register_command(self, cli_group: Group):
        cli_group.add_command(self.main, self.name)


class PluginManager:
    __instance = None
    entry_point = "ouranos.plugins"

    def __new__(cls):
        if cls.__instance is None:
            self = super().__new__(cls)
            cls.__instance = self
        return cls.__instance

    def register_plugins(self, cli_group: Group):
        for entry_point in entry_points(group=self.entry_point):
            pkg_name = entry_point.name
            pkg = importlib.import_module(pkg_name)
            try:
                plugin: Plugin = pkg.plugin
            except AttributeError as e:
                raise AttributeError(
                    f"Plugin `{pkg_name}` has no `plugin` defined"
                )
            else:
                plugin.register_command(cli_group)
