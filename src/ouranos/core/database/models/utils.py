from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
import datetime as dt
from typing import Any

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


class StmtModifier(ABC):
    @abstractmethod
    def modify_stmt(self, stmt: Select, column) -> Select: ...


@dataclass(frozen=True)
class HigherThan(StmtModifier):
    low_limit: int | float | dt.datetime | None

    def modify_stmt(self, stmt: Select, column) -> Select:
        if self.low_limit is not None:
            return stmt.where(column > self.low_limit)
        return stmt


@dataclass(frozen=True)
class LowerThan(StmtModifier):
    high_limit: int | float | dt.datetime | None

    def modify_stmt(self, stmt: Select, column) -> Select:
        if self.high_limit is not None:
            return stmt.where(column <= self.high_limit)
        return stmt


@dataclass(frozen=True)
class Between(LowerThan, HigherThan):
    def modify_stmt(self, stmt: Select, column) -> Select:
        if self.low_limit is not None:
            stmt = stmt.where(column > self.low_limit)
        if self.high_limit is not None:
            stmt = stmt.where(column <= self.high_limit)
        return stmt


@dataclass(frozen=True)
class Within(StmtModifier):
    choices: list[Any] | None

    def modify_stmt(self, stmt: Select, column) -> Select:
        if self.choices is not None:
            return stmt.where(column.in_(self.choices))
        return stmt
