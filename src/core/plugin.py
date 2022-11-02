import importlib
import pkgutil

from click import Group


class PluginManager:
    __instance = None
    plugins_prefix = "ouranos_"

    def __new__(cls):
        if cls.__instance is None:
            self = super().__new__(cls)
            cls.__instance = self
        return cls.__instance

    @classmethod
    def register_plugins(cls, cli: Group):
        for entry_point in pkgutil.iter_modules():
            pkg_name = entry_point.name
            if pkg_name.startswith(cls.plugins_prefix):
                name = pkg_name.lstrip(cls.plugins_prefix)
                pkg = importlib.import_module(pkg_name)
                try:
                    cli.add_command(pkg.main, name)
                except Exception as e:
                    raise AttributeError(
                        f"Package `{pkg_name}` has no method `name` implemented"
                    )
