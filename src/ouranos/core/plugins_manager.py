from __future__ import annotations

from importlib.metadata import entry_points
from logging import getLogger, Logger
from typing import Iterator

from fastapi import APIRouter, FastAPI
from fastapi.responses import JSONResponse

from ouranos import current_app
from ouranos.sdk import Plugin


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

    def _get_omitted(self) -> set:
        omitted_str = current_app.config["PLUGINS_OMITTED"]
        if omitted_str is not None:
            omitted = set(omitted_str.split(","))
        else:
            omitted = set()
        if not current_app.config["TESTING"]:
            omitted.add(self.test_plugin_name)
        return omitted

    def iter_entry_points(self) -> Iterator[Plugin]:
        for entry_point in entry_points(group=self.entry_point):
            pkg = entry_point.load()
            if isinstance(pkg, Plugin):
                yield pkg

    def iter_plugins(self, omit_excluded: bool = True) -> Iterator[Plugin]:
        from ouranos.aggregator.main import aggregator_plugin
        from ouranos.web_server.main import web_server_plugin

        entry_plugins = [plugin for plugin in self.iter_entry_points()]
        entry_plugins.sort()

        plugins = [aggregator_plugin, web_server_plugin, *entry_plugins]

        for plugin in plugins:
            # During testing, we only want to yield the test plugin
            if current_app.config["TESTING"]:
                if plugin.name == self.test_plugin_name:
                    yield plugin
                else:
                    continue

            # In production, we don't want to yield the test plugin
            if not current_app.config["DEVELOPMENT"]:
                if plugin.name == self.test_plugin_name:
                    continue

            if not omit_excluded:
                yield plugin

            if plugin.name not in self.omitted:
                yield plugin

    def register_plugins(self, omit_excluded: bool = True) -> None:
        if not self.plugins:
            for plugin in self.iter_plugins(omit_excluded):
                self.plugins[plugin.name] = plugin

    def get_plugin(self, plugin_name: str) -> Plugin | None:
        return self.plugins.get(plugin_name)

    async def start_plugins(self) -> None:
        for plugin_name in self.plugins:
            await self.start_plugin(plugin_name)

    async def start_plugin(self, plugin_name: str) -> None:
        plugin = self.get_plugin(plugin_name)
        if plugin is None:
            raise ValueError(f"Plugin {plugin_name} not found")
        plugin.setup_config(current_app.config)
        await plugin.startup()

    async def stop_plugins(self) -> None:
        for plugin_name in self.plugins:
            await self.stop_plugin(plugin_name)

    async def stop_plugin(self, plugin_name: str) -> None:
        plugin = self.get_plugin(plugin_name)
        if plugin is None:
            raise ValueError(f"Plugin {plugin_name} not found")
        await plugin.shutdown()

    def register_plugins_routes(
            self,
            router: APIRouter | FastAPI,
            json_response: JSONResponse = JSONResponse,
    ) -> None:
        if not self.plugins:
            raise RuntimeError("Plugins should be registered first.")
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
