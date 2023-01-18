from __future__ import annotations

import typing as t

from click import Command
from fastapi import APIRouter, FastAPI

from ouranos.sdk import Functionality


if t.TYPE_CHECKING:
    from ouranos.core.config import profile_type


class Plugin:
    def __init__(self, functionality: Functionality) -> None:
        self._functionality: Functionality = functionality

    @property
    def command(self) -> Command:
        pass


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
