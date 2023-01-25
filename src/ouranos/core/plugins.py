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

from ouranos.core.utils import stripped_warning
from ouranos.sdk import AddOn, Functionality, Plugin


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
        self.excluded: set = set()
        self.plugins: dict[str, Plugin] = {}
        self.functionalities: dict[str, Functionality] = {}

    def iter_entry_points(
            self,
            omit_excluded: bool = True
    ) -> Iterator:
        args = inspect.signature(entry_points).parameters
        if "group" in args:
            entry_points_ = entry_points(group=self.entry_point)
        # Python < 3.10
        else:
            grouped_entry_points = entry_points()
            entry_points_ = grouped_entry_points.get(self.entry_point, [])
        for entry_point in entry_points_:
            if not omit_excluded:
                yield entry_point
            else:
                if entry_point.name not in self.excluded:
                    yield entry_point

    def register_new_functionalities(
            self,
            router: APIRouter | FastAPI,
            omit_excluded: bool = True
    ) -> None:
        for entry_point in self.iter_entry_points(omit_excluded):
            pkg = entry_point.load()
            if isinstance(pkg, Plugin):
                self.plugins[pkg.name] = pkg
            elif isinstance(pkg, AddOn):
                self.register_addon(pkg, router)
                pass
            else:
                message = f"{pkg.__class__.__name__} is not a valid plugin or addon"
                self.logger.error(message)
                stripped_warning(message)

    def register_plugins(self, omit_excluded: bool = True) -> None:
        for entry_point in self.iter_entry_points(omit_excluded):
            pkg = entry_point.load()
            if isinstance(pkg, Plugin):
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

    def register_addons(
            self,
            router: APIRouter | FastAPI,
            json_response: JSONResponse = JSONResponse,
            omit_excluded: bool = True
    ) -> None:
        for entry_point in self.iter_entry_points(omit_excluded):
            pkg = entry_point.load()
            if isinstance(pkg, AddOn):
                self.register_addon(pkg, router, json_response)

    @staticmethod
    def register_addon(
            addon: AddOn,
            router: APIRouter | FastAPI,
            json_response: JSONResponse = JSONResponse
    ) -> None:
        addon_routes = APIRouter(prefix=f"/{AddOn.name}")
        for route in addon.routes:
            router.default_response_class = json_response
            router.add_route(route.path, route.endpoint)
