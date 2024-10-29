from __future__ import annotations

from importlib.metadata import entry_points
from logging import getLogger, Logger
from typing import Iterator

from fastapi import APIRouter, FastAPI
from fastapi.responses import JSONResponse

from ouranos import current_app
from ouranos.sdk import Functionality, Plugin


class PluginManager:
    __instance = None
    entry_point = "ouranos.plugins"
    test_plugin_name = "dummy-plugin"

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
            omitted.add(self.test_plugin_name)
        return omitted

    def iter_entry_points(
            self,
            omit_excluded: bool = True
    ) -> Iterator[Plugin]:
        for entry_point in entry_points(group=self.entry_point):
            pkg = entry_point.load()
            if isinstance(pkg, Plugin):
                if current_app.config["TESTING"]:
                    if pkg.name == self.test_plugin_name:
                        yield pkg
                    else:
                        continue

                if not omit_excluded:
                    yield pkg

                if pkg.name not in self.omitted:
                    yield pkg

    def register_plugins(self, omit_excluded: bool = True) -> None:
        if not self.plugins:
            for pkg in self.iter_entry_points(omit_excluded):
                self.plugins[pkg.name] = pkg

    def init_plugins(self, microservice: bool = True):
        plugins = [*self.plugins]
        plugins.sort()
        for plugin_name in plugins:
            self.init_plugin(plugin_name, microservice)

    def init_plugin(self, plugin_name: str, microservice: bool = True):
        plugin = self.plugins[plugin_name]
        functionality_cls = plugin.functionality_cls
        self.functionalities[plugin_name] = functionality_cls(
            microservice=microservice)

    async def start_plugins(self):
        for plugin_name in self.functionalities:
            await self.start_plugin(plugin_name)

    async def start_plugin(self, plugin_name):
        await self.functionalities[plugin_name].startup()

    async def stop_plugins(self):
        for plugin_name in self.functionalities:
            await self.stop_plugin(plugin_name)

    async def stop_plugin(self, plugin_name):
        await self.functionalities[plugin_name].shutdown()

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
