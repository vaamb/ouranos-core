from __future__ import annotations

import typing as t
from typing import Callable


if t.TYPE_CHECKING:
    from ouranos.aggregator.events import Events


data_type: dict | list | str | tuple


def registration_required(func: Callable):
    """Decorator which makes sure the engine is registered and injects
    engine_uid"""
    async def wrapper(self: "Events", sid: str, data: data_type):
        async with self.session(sid, namespace="/gaia") as session:
            engine_uid = session.get("engine_uid")
        if not engine_uid:
            await self.disconnect(sid, namespace="/gaia")
        else:
            return await func(self, sid, data, engine_uid)
    return wrapper


def dispatch_to_application(func: Callable):
    """Decorator which dispatch the data to the clients namespace"""
    async def wrapper(self: "Events", sid: str, data: data_type, *args):
        func_name: str = func.__name__
        event: str = func_name.lstrip("on_")
        await self.dispatcher.emit(
            event, data=data, namespace="application", ttl=15
        )
        return await func(self, sid, data, *args)
    return wrapper
