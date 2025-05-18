from __future__ import annotations

import asyncio
from collections import namedtuple
from typing import Type, TypeVar

from click import Command, Option

from ouranos.sdk import Functionality, run_functionality_forever


F = TypeVar("F", bound=Functionality)

Route = namedtuple("Route", ("path", "endpoint"))


class Plugin:
    def __init__(
            self,
            functionality: Type[F],
            name: str | None = None,
            command: Command | None = None,
            routes: list[Route] | None = None,
            **kwargs,
    ) -> None:
        self._functionality: Type[F] = functionality
        self._kwargs = kwargs
        self._instance: F | None = None
        self.name: str = name or functionality.__name__.lower()
        self._command: Command | None = command
        self._routes: list[Route] = routes or []

    @property
    def functionality_cls(self) -> Type[F]:
        return self._functionality

    @property
    def instance(self) -> F:
        return self._instance

    def has_command(self) -> bool:
        return self._command is not None

    @property
    def command(self) -> Command:
        if self._command is None:
            func = asyncio.run(
                run_functionality_forever(self.functionality_cls)
            )
            command = Command("main", callback=func)
            option = Option(
                "--config-profile",
                type=str,
                default=None,
                help="Configuration profile to use as defined in config.py.",
                show_default=True
            )
            command.params.append(option)
            self._command = command
        return self._command

    def has_route(self) -> bool:
        return len(self._routes) > 0

    def add_route(self, route: Route) -> None:
        self._routes.append(route)

    @property
    def routes(self) -> list[Route]:
        return self._routes
