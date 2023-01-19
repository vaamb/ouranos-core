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
        self.name = self._functionality.__class__.__name__

    @property
    def command(self) -> Command:
        pass


class AddOn:
    def __init__(
            self,
    ) -> None:
        self._endpoints: list[APIRouter] = []

    def add_endpoint(self, endpoint) -> None:
        self._endpoints.append(endpoint)

    def register_endpoints(self, router: APIRouter | FastAPI) -> None:
        for endpoint in self._endpoints:
            router.include_router(endpoint)

    @property
    def endpoints(self) -> list[APIRouter]:
        return self._endpoints
