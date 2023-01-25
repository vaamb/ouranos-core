from __future__ import annotations

from collections import namedtuple
import re
from typing import Type

from click import Command

from ouranos.sdk import Functionality


pattern = re.compile(r'(?<!^)(?=[A-Z])')
Route = namedtuple("Route", ("path", "endpoint"))


class Plugin:
    def __init__(
            self,
            functionality: Type[Functionality],
            command: Command
    ) -> None:
        self._functionality: Type[Functionality] = functionality
        self.command: Command = command
        self.name = self._functionality.__class__.__name__

    @property
    def functionality_cls(self) -> Type[Functionality]:
        return self._functionality


class AddOn:
    def __init__(
            self,
            routes: list[Route] | None = None
    ) -> None:
        self.name = pattern.sub('_', self.__class__.__name__).lower()
        self._routes: list[Route] = routes or []

    def add_route(self, route: Route) -> None:
        self._routes.append(route)

    @property
    def routes(self) -> list[Route]:
        return self._routes
