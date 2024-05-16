from __future__ import annotations

from datetime import datetime
from typing import Optional, Self, Sequence

from asyncache import cached
from cachetools import TTLCache
import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql.functions import max as sa_max

from ouranos.core.database.models.abc import (
    Base, CacheMixin, CRUDMixin, RecordMixin)
from ouranos.core.database.models.types import UtcDateTime
from ouranos.core.database.models.utils import sessionless_hashkey
from ouranos.core.utils import timeWindow


_cache_system_history = TTLCache(maxsize=1, ttl=10)


# ---------------------------------------------------------------------------
#   System-related models, located in db_system
# ---------------------------------------------------------------------------
class System(Base, CRUDMixin):
    __tablename__ = "systems"
    __bind_key__ = "system"

    id: Mapped[int] = mapped_column(primary_key=True)
    uid: Mapped[str] = mapped_column(sa.String(32))
    RAM_total: Mapped[float] = mapped_column(sa.Float(precision=2))
    DISK_total: Mapped[float] = mapped_column(sa.Float(precision=2))


# ---------------------------------------------------------------------------
#   SystemData-related models, located in db_system
# ---------------------------------------------------------------------------
class BaseSystemData(Base):
    __abstract__ = True

    id: Mapped[int] = mapped_column(primary_key=True)
    system_uid: Mapped[str] = mapped_column(sa.String(32), default="NA")
    timestamp: Mapped[datetime] = mapped_column(UtcDateTime)
    CPU_used: Mapped[float] = mapped_column(sa.Float(precision=1))
    CPU_temp: Mapped[Optional[float]] = mapped_column(sa.Float(precision=1))
    RAM_total: Mapped[float] = mapped_column(sa.Float(precision=2))
    RAM_used: Mapped[float] = mapped_column(sa.Float(precision=2))
    RAM_process: Mapped[float] = mapped_column(sa.Float(precision=2))
    DISK_total: Mapped[float] = mapped_column(sa.Float(precision=2))
    DISK_used: Mapped[float] = mapped_column(sa.Float(precision=2))


class SystemDataRecord(BaseSystemData, RecordMixin):
    __tablename__ = "system_records"
    __bind_key__ = "system"

    @classmethod
    async def get_records(
            cls,
            session: AsyncSession,
            time_window: timeWindow
    ) -> Sequence[Self]:
        stmt = (
            select(cls)
            .where(
                (cls.timestamp > time_window.start) &
                (cls.timestamp <= time_window.end)
            )
        )
        result = await session.execute(stmt)
        return result.scalars().all()

    @classmethod
    @cached(_cache_system_history, key=sessionless_hashkey)
    async def get_timed_values(
            cls,
            session: AsyncSession,
            time_window: timeWindow
    ) -> list[tuple[datetime, str, float, Optional[float], float, float, float,
                    float, float]]:
        stmt = (
            select(
                cls.timestamp, cls.system_uid, cls.CPU_used, cls.CPU_temp,
                cls.RAM_process, cls.RAM_used, cls.RAM_total, cls.DISK_used,
                cls.DISK_total
            )
            .where(
                (cls.timestamp > time_window.start) &
                (cls.timestamp <= time_window.end)
            )
        )
        result = await session.execute(stmt)
        return [r._data for r in result.all()]


class SystemDataCache(BaseSystemData, CacheMixin):
    __tablename__ = "system_temp"
    __bind_key__ = "memory"

    @classmethod
    def get_ttl(cls) -> int:
        return 90

    @classmethod
    async def get_recent(
            cls,
            session: AsyncSession,
            system_uid: str | list | None = None
    ) -> Sequence[Self]:
        await cls.remove_expired(session)
        sub_stmt = (
            select(cls.id, sa_max(cls.timestamp))
            .group_by(cls.system_uid)
            .subquery()
        )
        stmt = select(cls).join(sub_stmt, cls.id == sub_stmt.c.id)
        if system_uid:
            if isinstance(system_uid, str):
                system_uid = [system_uid, ]
            stmt = stmt.where(cls.system_uid.in_(system_uid))
        result = await session.execute(stmt)
        return result.scalars().all()

    @classmethod
    async def get_recent_timed_values(
            cls,
            session: AsyncSession,
            system_uid: str | list | None = None
    ) -> list[
        tuple[datetime, str, float, Optional[float], float, float, float,
              float, float]
    ]:
        await cls.remove_expired(session)
        sub_stmt = (
            select(cls.id, sa_max(cls.timestamp))
            .group_by(cls.system_uid)
            .subquery()
        )
        stmt = select(
            cls.timestamp, cls.system_uid, cls.CPU_used, cls.CPU_temp,
            cls.RAM_process, cls.RAM_used, cls.RAM_total, cls.DISK_used,
            cls.DISK_total
        ).join(sub_stmt, cls.id == sub_stmt.c.id)
        if system_uid:
            if isinstance(system_uid, str):
                system_uid = [system_uid, ]
            stmt = stmt.where(cls.system_uid.in_(system_uid))
        result = await session.execute(stmt)
        return [r._data for r in result.all()]
