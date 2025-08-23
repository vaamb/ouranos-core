from __future__ import annotations

from sqlalchemy.sql.selectable import Select


class TIME_LIMITS:
    RECENT: int = 36
    SENSORS: int = 24 * 7
    HEALTH: int = 24 * 31
    WARNING: int = 24 * 7


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
