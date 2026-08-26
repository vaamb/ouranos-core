from __future__ import annotations

from importlib.metadata import entry_points, EntryPoint
from logging import getLogger, Logger

from fastapi import APIRouter, FastAPI
from fastapi.responses import JSONResponse

from ouranos import current_app
from ouranos.sdk import Plugin


class PluginManager:
    __instance = None
    entry_point = "ouranos.plugins"
    test_plugin_name = "dummy"

    def __new__(cls):
        if cls.__instance is None:
            self = super().__new__(cls)
            cls.__instance = self
        return cls.__instance

    def __init__(self):
        self.logger: Logger = getLogger("ouranos.plugin_manager")
        self.omitted: set = self._get_omitted()
        self._entry_points: dict[str, EntryPoint] | None = None
        self._plugins: dict[str, Plugin] | None = None

    @property
    def entry_points(self) -> dict[str, EntryPoint]:
        if self._entry_points is None:
            entry_points_dct: dict[str, EntryPoint] = {}
            entry_point_lst = [_ for _ in entry_points(group=self.entry_point)]
            entry_point_lst.sort()
            for entry_point in entry_point_lst:
                entry_points_dct[entry_point.name] = entry_point
            self._entry_points = entry_points_dct
        assert self._entry_points is not None
        return self._entry_points

    @property
    def plugins(self) -> dict[str, Plugin]:
        if self._plugins is None:
            raise ValueError("Plugins should be registered first.")
        assert self._plugins is not None
        return self._plugins

    @property
    def _core_plugins(self) -> dict[str, Plugin]:
        from ouranos.aggregator.main import aggregator_plugin
        from ouranos.web_server.main import web_server_plugin

        return {
            aggregator_plugin.name: aggregator_plugin,
            web_server_plugin.name: web_server_plugin,
        }

    def _get_omitted(self) -> set:
        omitted_str = current_app.config["PLUGINS_OMITTED"] or ""

        omitted = {plugin.replace("-", "_") for plugin in omitted_str.split(",")}

        if not current_app.config["TESTING"]:
            omitted.add(self.test_plugin_name)
        return omitted

    def _load_plugin_from_entry_point(self, entry_point: EntryPoint) -> Plugin:
        pkg = entry_point.load()
        if isinstance(pkg, Plugin):
            if entry_point.name != pkg.name:
                raise ValueError(
                    f"Entry point and plugin names dont match for plugin "
                    f"`{pkg.__class__.__name__}`"
                )
            return pkg
        raise ValueError(
            f"EntryPoint '{entry_point.name}' does not contain a plugin."
        )

    def load_plugin(self, plugin_name: str) -> Plugin:
        # Try to get the plugin from the shipped ones
        plugin = self._core_plugins.get(plugin_name)
        if plugin is not None:
            return plugin

        # Try to get the plugin from the entry points. This assumes entry points
        # and the plugin they contain share the same name
        entry_point = self.entry_points.get(plugin_name)
        if entry_point is None:
            raise ValueError(f"Plugin '{plugin_name}' not found")
        return self._load_plugin_from_entry_point(entry_point)

    def _is_plugin_needed(self, plugin_name: str, omit_excluded: bool = True) -> bool:
        plugin_name_formatted = plugin_name.replace("-", "_")
        if current_app.config["TESTING"]:
            return plugin_name_formatted == self.test_plugin_name

        # In production, we don't want to yield the test plugin
        if not current_app.config["DEVELOPMENT"]:
            if plugin_name_formatted == self.test_plugin_name:
                return False

        if not omit_excluded:
            return True

        return plugin_name_formatted not in self.omitted

    def register_plugins(self, omit_excluded: bool = True) -> None:
        if self._plugins is not None:
            raise RuntimeError("Plugins have already been registered.")

        plugins: dict[str, Plugin] = {}

        for plugin_name, plugin in self._core_plugins.items():
            if self._is_plugin_needed(plugin_name, omit_excluded):
                plugins[plugin_name] = plugin

        for plugin_name, entry_point in self.entry_points.items():
            if not self._is_plugin_needed(plugin_name, omit_excluded):
                continue

            try:
                plugins[plugin_name] = self._load_plugin_from_entry_point(entry_point)
            except Exception as e:
                self.logger.error(
                    f"Failed to register plugin '{plugin_name}': {e}")

        self._plugins = plugins

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
        if not self._plugins:
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
