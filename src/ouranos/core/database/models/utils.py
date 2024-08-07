from __future__ import annotations

from typing import Any, Type

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.selectable import Select

from ouranos.core.database.models.abc import Base


class TIME_LIMITS:
    RECENT: int = 36
    SENSORS: int = 24 * 7
    HEALTH: int = 24 * 31
    WARNING: int = 24 * 7


def create_hashable_key(**kwargs: dict[str: Any]) -> tuple:
    to_freeze = []
    def append_if_hashable(key: str, value: Any) -> None:
        nonlocal to_freeze
        try:
            hash(value)
        except TypeError:
            raise TypeError(f"Cannot hash {key}'s value {value}")
        else:
            to_freeze.append((key, value))

    for key, value in sorted(kwargs.items()):
        if isinstance(value, list):
            frozen_value = tuple(value)
            append_if_hashable(key, frozen_value)
        #elif isinstance(value, dict):
        #    to_freeze.append((key, create_hashable_key(**value)))
        else:
            append_if_hashable(key, value)
    return tuple(to_freeze)


def sessionless_hashkey(
        cls_or_self: Type[Base] | Base,
        session: AsyncSession,
        /,
        **kwargs
) -> tuple:
    if isinstance(cls_or_self, Base):
        if hasattr(cls_or_self, "id"):
            kwargs["id"] = cls_or_self.id
        if hasattr(cls_or_self, "uid"):
            kwargs["uid"] = cls_or_self.uid
    return create_hashable_key(**kwargs)


def paginate(
        stmt: Select,
        page: int | None = None,
        per_page: int | None = None
) -> Select:
    page = page or 1
    if page < 1:
        page = 1
    per_page = per_page or 20
    if per_page < 1:
        per_page = 20
    offset = (page - 1) * per_page
    return stmt.offset(offset).limit(per_page)
