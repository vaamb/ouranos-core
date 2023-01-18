from __future__ import annotations

import typing as t

from click import Command, Group
from fastapi import APIRouter, FastAPI

from ouranos.sdk import Functionality


if t.TYPE_CHECKING:
    from ouranos.core.config import profile_type


class Plugin(Functionality):
    def __init__(
            self,
            config_profile: "profile_type" = None,
            config_override: dict | None = None
    ) -> None:

        super().__init__(config_profile, config_override)
        self.commands: dict[str, Command] = {}

    def add_command(self, command: dict[str, Command]) -> None:
        self.commands.update(command)

    def register_commands(self, cli_group: Group) -> None:
        for name, command in self.commands.items():
            cli_group.add_command(command, name)


class AddOn:
    def __init__(
            self,
    ) -> None:
        self.endpoints: list[APIRouter] = []

    def add_endpoint(self, endpoint) -> None:
        self.endpoints.append(endpoint)

    def register_endpoints(self, router: APIRouter | FastAPI) -> None:
        for endpoint in self.endpoints:
            router.include_router(endpoint)
