from __future__ import annotations

import importlib
try:
    from importlib_metadata import entry_points
except ImportError:
    from importlib.metadata import entry_points
import typing as t
from typing import Iterator

from click import Group
from fastapi import APIRouter, FastAPI


if t.TYPE_CHECKING:
    from ouranos.sdk.plugin import Plugin


class PluginManager:
    __instance = None
    entry_point = "ouranos.plugins"

    def __new__(cls):
        if cls.__instance is None:
            self = super().__new__(cls)
            cls.__instance = self
        return cls.__instance

    def iter_plugins(self) -> Iterator["Plugin"]:
        for entry_point in entry_points(group=self.entry_point):
            try:
                plugin: "Plugin" = entry_point.load()
                yield plugin
            except ImportError:
                raise ImportError(
                    f"Plugin `{entry_point.name}` has no `plugin` defined"
                )

    def register_commands(self, cli_group: Group) -> None:
        for plugin in self.iter_plugins():
            plugin.register_commands(cli_group)

    def register_endpoints(self, router: APIRouter | FastAPI) -> None:
        for plugin in self.iter_plugins():
            plugin.register_endpoints(router)
