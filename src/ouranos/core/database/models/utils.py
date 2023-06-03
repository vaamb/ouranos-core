from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal, Type

from cachetools import cached, TTLCache
from cachetools.keys import hashkey
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.selectable import Select

from ouranos.core.database.models.common import Base


_timelimit_cache = TTLCache(maxsize=1, ttl=5)


time_limits_category: Literal["recent", "sensors", "health", "warnings"]


def sessionless_hashkey(
        cls_or_self: Type | Base,
        session: AsyncSession,
        *args,
        **kwargs
) -> tuple:
    inst_ids = []
    if isinstance(cls_or_self, Base):
        for id_ in ("uid", "id"):
            if hasattr(cls_or_self, id_):
                inst_ids.append(getattr(cls_or_self, id_))
    return hashkey(*inst_ids, *args, **kwargs)


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


@cached(_timelimit_cache)
def _time_limits() -> dict[time_limits_category, datetime]:
    now_utc = datetime.now(timezone.utc)
    return {
        "recent": (now_utc - timedelta(hours=36)),
        "sensors": (now_utc - timedelta(days=7)),
        "health": (now_utc - timedelta(days=31)),
        "warnings": (now_utc - timedelta(days=7)),
    }


def time_limits(category: time_limits_category) -> datetime:
    return _time_limits()[category]
