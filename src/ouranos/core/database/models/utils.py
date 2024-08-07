from __future__ import annotations

from typing import Any, Type

from cachetools.keys import hashkey
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.selectable import Select

from ouranos.core.database.models.abc import Base


class TIME_LIMITS:
    RECENT: int = 36
    SENSORS: int = 24 * 7
    HEALTH: int = 24 * 31
    WARNING:int = 24 * 7


def sessionless_hashkey(
        cls_or_self: Type | Base,
        session: AsyncSession,
        /,
        **kwargs
) -> tuple:
    inst_ids = []
    if isinstance(cls_or_self, Base):
        for id_ in ("uid", "id"):
            if hasattr(cls_or_self, id_):
                inst_ids.append(getattr(cls_or_self, id_))
    unlisted_kwargs: list[Any] = []
    for key in sorted(kwargs.keys()):
        if isinstance(kwargs[key], list):
            unlisted_kwargs.append(tuple(kwargs[key]))
        else:
            unlisted_kwargs.append(kwargs[key])
    return hashkey(*inst_ids, *unlisted_kwargs)


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
