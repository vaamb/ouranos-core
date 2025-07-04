from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional, Self, Sequence

import sqlalchemy as sa
from sqlalchemy import select, UniqueConstraint
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql.functions import func, max as sa_max

from ouranos.core.database.models.abc import Base, CacheMixin, RecordMixin
from ouranos.core.database.models.caches import (
    cache_systems, cache_systems_history)
from ouranos.core.database.models.caching import (
    cached, CachedCRUDMixin, sessionless_hashkey)
from ouranos.core.database.models.types import UtcDateTime
from ouranos.core.utils import timeWindow


timed_value = list[
    tuple[datetime, float, Optional[float], float, float, float]
]


# ---------------------------------------------------------------------------
#   System-related models, located in db_system
# ---------------------------------------------------------------------------
class System(Base, CachedCRUDMixin):
    __tablename__ = "systems"
    __bind_key__ = "system"
    _cache = cache_systems

    uid: Mapped[str] = mapped_column(sa.String(32), primary_key=True)
    hostname: Mapped[str] = mapped_column(sa.String(32), default="_default")
    start_time: Mapped[datetime] = mapped_column(UtcDateTime, default=func.current_timestamp())
    RAM_total: Mapped[float] = mapped_column(sa.Float(precision=2))
    DISK_total: Mapped[float] = mapped_column(sa.Float(precision=2))

    async def get_recent_timed_values(
            self,
            session: AsyncSession,
    ) -> list[timed_value]:
        return await SystemDataCache.get_recent_timed_values(
            session, system_uid=self.uid)

    async def get_timed_values(
            self,
            session: AsyncSession,
            time_window: timeWindow,
    ) -> list[timed_value]:
        return await SystemDataRecord.get_timed_values(
            session, time_window=time_window, system_uid=self.uid)


# ---------------------------------------------------------------------------
#   SystemData-related models, located in db_system
# ---------------------------------------------------------------------------
class BaseSystemData(Base):
    __abstract__ = True

    id: Mapped[int] = mapped_column(primary_key=True)
    system_uid: Mapped[str] = mapped_column(sa.ForeignKey("systems.uid"))
    timestamp: Mapped[datetime] = mapped_column(UtcDateTime, default=func.current_timestamp())
    CPU_used: Mapped[float] = mapped_column(sa.Float(precision=1))
    CPU_temp: Mapped[Optional[float]] = mapped_column(sa.Float(precision=1))
    RAM_used: Mapped[float] = mapped_column(sa.Float(precision=2))
    RAM_process: Mapped[float] = mapped_column(sa.Float(precision=2))
    DISK_used: Mapped[float] = mapped_column(sa.Float(precision=2))


class SystemDataRecord(BaseSystemData, RecordMixin):
    __tablename__ = "system_records"
    __bind_key__ = "system"

    @classmethod
    async def get_records(
            cls,
            session: AsyncSession,
            time_window: timeWindow,
            system_uid: str | list | None = None,
    ) -> Sequence[Self]:
        stmt = (
            select(cls)
            .where(
                (cls.timestamp > time_window.start) &
                (cls.timestamp <= time_window.end)
            )
            .order_by(cls.timestamp.asc())
        )
        if system_uid:
            if isinstance(system_uid, str):
                system_uid = [system_uid, ]
            stmt = stmt.where(cls.system_uid.in_(system_uid))
        result = await session.execute(stmt)
        return result.scalars().all()

    @classmethod
    @cached(cache_systems_history, key=sessionless_hashkey)
    async def get_timed_values(
            cls,
            session: AsyncSession,
            *,
            time_window: timeWindow,
            system_uid: str | list | None = None,
    ) -> list[timed_value]:
        stmt = (
            select(
                cls.timestamp, cls.CPU_used, cls.CPU_temp, cls.RAM_process,
                cls.RAM_used, cls.DISK_used,
            )
            .where(
                (cls.timestamp > time_window.start) &
                (cls.timestamp <= time_window.end)
            )
            .order_by(cls.timestamp.asc())
        )
        if system_uid:
            if isinstance(system_uid, str):
                system_uid = [system_uid, ]
            stmt = stmt.where(cls.system_uid.in_(system_uid))
        result = await session.execute(stmt)
        return result.all()


class SystemDataCache(BaseSystemData, CacheMixin):
    __tablename__ = "system_temp"
    __bind_key__ = "transient"
    __table_args__ = (
        UniqueConstraint(
            "system_uid",
            name="_no_repost_constraint"
        ),
    )

    @classmethod
    def get_ttl(cls) -> int:
        return 90

    @classmethod
    async def get_recent_timed_values(
            cls,
            session: AsyncSession,
            /,
            system_uid: str | list | None = None
    ) -> list[timed_value]:
        time_limit = datetime.now(timezone.utc) - timedelta(seconds=cls.get_ttl())
        stmt = (
            select(
                cls.timestamp, cls.CPU_used, cls.CPU_temp, cls.RAM_process,
                cls.RAM_used, cls.DISK_used,
            )
            .where(cls.timestamp > time_limit)
        )
        if system_uid:
            if isinstance(system_uid, str):
                system_uid = [system_uid, ]
            stmt = stmt.where(cls.system_uid.in_(system_uid))
        result = await session.execute(stmt)
        return result.all()
