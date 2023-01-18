from __future__ import annotations

try:
    from importlib.metadata import entry_points
except ImportError:
    from importlib_metadata import entry_points
from typing import Iterator

from fastapi import APIRouter, FastAPI

from ouranos.sdk.plugin import AddOn, Plugin


class PluginManager:
    __instance = None
    entry_point = "ouranos.plugins"

    def __new__(cls):
        if cls.__instance is None:
            self = super().__new__(cls)
            cls.__instance = self
        return cls.__instance

    def __init__(self):
        self.plugins: dict[str, Plugin] = {}
        self.excluded: set = set()

    def iter_entry_points(
            self,
            omit_excluded: bool = True
    ) -> Iterator:
        for entry_point in entry_points(group=self.entry_point):
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
                self.register_plugin(pkg)
            elif isinstance(pkg, AddOn):
                self.register_addon(pkg, router)
            else:
                # TODO: use warning
                print(f"{pkg.__class__.__name__} iis not a plugin or an addon")

    def register_plugin(self, plugin: Plugin) -> None:
        #TODO
        self.plugins[plugin.name] = plugin

    def register_addon(self, addon: AddOn, router: APIRouter | FastAPI) -> None:
        #TODO
        pass
