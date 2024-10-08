from __future__ import annotations

import typing as t
from typing import Callable
from uuid import UUID

from ouranos.core.exceptions import NotRegisteredError


if t.TYPE_CHECKING:
    from ouranos.aggregator.events import Events


data_type: dict | list | str | tuple | None


def registration_required(func: Callable):
    """Decorator which makes sure the engine is registered and injects
    engine_uid"""
    async def wrapper(self: "Events", sid: UUID, data: data_type = None):
        async with self.session(sid) as session:
            engine_uid: str | None = session.get("engine_uid")
        if engine_uid is None:
            raise NotRegisteredError(f"Engine with sid {sid} is not registered.")
        else:
            if data is not None:
                return await func(self, sid, data, engine_uid)
            return await func(self, sid, engine_uid)
    return wrapper


def dispatch_to_application(func: Callable):
    """Decorator which dispatch the data to the clients namespace"""
    async def wrapper(self: "Events", sid: str, data: data_type, *args):
        func_name: str = func.__name__
        event: str = func_name.lstrip("on_")
        await self.internal_dispatcher.emit(
            event, data=data, namespace="application-internal", ttl=15)
        return await func(self, sid, data, *args)
    return wrapper
