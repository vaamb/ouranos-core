from __future__ import annotations

from click import Command, Group
from fastapi import APIRouter, FastAPI


class Plugin:
    def __init__(
            self,
    ) -> None:
        self.commands: dict[str, Command] = {}
        self.endpoints: list[APIRouter] = []

    def add_command(self, command: dict[str, Command]) -> None:
        self.commands.update(command)

    def register_commands(self, cli_group: Group) -> None:
        for name, command in self.commands.items():
            cli_group.add_command(command, name)

    def add_endpoint(self, endpoint) -> None:
        self.endpoints.append(endpoint)

    def register_endpoints(self, router: APIRouter | FastAPI) -> None:
        for endpoint in self.endpoints:
            router.include_router(endpoint)
