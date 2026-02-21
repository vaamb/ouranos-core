from __future__ import annotations

from collections import deque
from typing import AsyncIterator, cast, TypedDict

from dispatcher import AsyncDispatcher


class EmitDict(TypedDict):
    event: str
    data: dict | list | str | tuple | None
    room: str
    namespace: str


class MockAsyncDispatcher(AsyncDispatcher):
    asyncio_based = True

    def __init__(self, namespace: str):
        super().__init__(namespace)
        self.emit_store: deque[EmitDict] = deque()

    async def _listen(self) -> AsyncIterator[bytes]:
        pass  # No used

    async def _publish(self, namespace: str, payload: bytes, ttl: int | None = None,
                       timeout: int | float | None = None) -> None:
        pass  # Short-circuited

    async def _broker_reachable(self) -> bool:
        return True

    async def emit(
            self,
            event: str,
            data: dict | list | str | tuple | None = None,
            to: dict | None = None,
            room: str | None = None,
            namespace: str | None = None,
            ttl: int | None = None,
            **kwargs
    ):
        self.emit_store.append(cast(EmitDict, {
            "event": event,
            "data": data,
            "room": room,
            "namespace": namespace,
        }))

    def clear_store(self):
        self.emit_store.clear()
