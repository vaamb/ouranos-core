from __future__ import annotations

try:
    from importlib.metadata import entry_points
except ImportError:
    from importlib_metadata import entry_points
import inspect
from logging import getLogger, Logger
from typing import Iterator

from fastapi import APIRouter, FastAPI
from fastapi.responses import JSONResponse

from ouranos import current_app
from ouranos.sdk import Functionality, Plugin


class PluginManager:
    __instance = None
    entry_point = "ouranos.plugins"

    def __new__(cls):
        if cls.__instance is None:
            self = super().__new__(cls)
            cls.__instance = self
        return cls.__instance

    def __init__(self):
        self.logger: Logger = getLogger("ouranos.plugin_manager")
        self.omitted: set = self._get_omitted()
        self.plugins: dict[str, Plugin] = {}
        self.functionalities: dict[str, Functionality] = {}

    def _get_omitted(self) -> set:
        omitted_str = current_app.config["PLUGINS_OMITTED"]
        if omitted_str is not None:
            omitted = set(omitted_str.split(","))
        else:
            omitted = set()
        if not current_app.config["TESTING"]:
            omitted.add("dummy")
        return omitted

    def iter_entry_points(
            self,
            omit_excluded: bool = True
    ) -> Iterator[Plugin]:
        args = inspect.signature(entry_points).parameters
        if "group" in args:
            entry_points_ = entry_points(group=self.entry_point)
        # Python < 3.10
        else:
            grouped_entry_points = entry_points()
            entry_points_ = grouped_entry_points.get(self.entry_point, [])
        for entry_point in entry_points_:
            pkg = entry_point.load()
            if not omit_excluded and isinstance(pkg, Plugin):
                yield pkg
            else:
                if isinstance(pkg, Plugin) and pkg.name not in self.omitted:
                    yield pkg

    def register_plugins(self, omit_excluded: bool = True) -> None:
        if not self.plugins:
            for pkg in self.iter_entry_points(omit_excluded):
                self.plugins[pkg.name] = pkg

    def init_plugins(self):
        plugins = [*self.plugins]
        plugins.sort()
        for plugin_name in plugins:
            self.init_plugin(plugin_name)

    def init_plugin(self, plugin_name):
        plugin = self.plugins[plugin_name]
        functionality_cls = plugin.functionality_cls
        self.functionalities[plugin_name] = functionality_cls()

    def start_plugins(self):
        for plugin_name in self.functionalities:
            self.start_plugin(plugin_name)

    def start_plugin(self, plugin_name):
        self.functionalities[plugin_name].start()

    def stop_plugins(self):
        for plugin_name in self.functionalities:
            self.stop_plugin(plugin_name)

    def stop_plugin(self, plugin_name):
        self.functionalities[plugin_name].stop()

    def register_plugins_routes(
            self,
            router: APIRouter | FastAPI,
            json_response: JSONResponse = JSONResponse,
    ) -> None:
        if not self.plugins:
            self.register_plugins()
        for pkg in self.plugins.values():
            if pkg.has_route():
                self.register_routes(pkg, router, json_response)

    def register_routes(
            self,
            plugin: Plugin,
            router: APIRouter | FastAPI,
            json_response: JSONResponse = JSONResponse
    ) -> None:
        self.logger.debug(f"Registering {plugin.name} routes")
        plugin_routes = APIRouter(prefix=f"/{plugin.name}")
        plugin_routes.default_response_class = json_response
        for route in plugin.routes:
            plugin_routes.add_route(route.path, route.endpoint)
        router.include_router(plugin_routes)
