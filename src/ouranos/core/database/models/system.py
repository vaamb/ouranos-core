from __future__ import annotations

from datetime import datetime
from typing import Optional, Self, Sequence

from asyncache import cached
from cachetools import TTLCache
import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql.functions import func, max as sa_max

from ouranos.core.database.models.abc import (
    Base, CacheMixin, CRUDMixin, RecordMixin)
from ouranos.core.database.models.types import UtcDateTime
from ouranos.core.database.models.utils import sessionless_hashkey
from ouranos.core.utils import timeWindow


_cache_system_history = TTLCache(maxsize=1, ttl=10)

timed_value = list[
    tuple[datetime, float, Optional[float], float, float, float]
]


# ---------------------------------------------------------------------------
#   System-related models, located in db_system
# ---------------------------------------------------------------------------
class System(Base, CRUDMixin):
    __tablename__ = "systems"
    __bind_key__ = "system"

    id: Mapped[int] = mapped_column(primary_key=True)
    uid: Mapped[str] = mapped_column(sa.String(32))
    start_time: Mapped[datetime] = mapped_column(UtcDateTime, default=func.current_timestamp())
    RAM_total: Mapped[float] = mapped_column(sa.Float(precision=2))
    DISK_total: Mapped[float] = mapped_column(sa.Float(precision=2))

    @classmethod
    async def get(cls, session: AsyncSession, uid: str) -> Self | None:
        stmt = select(cls).where(cls.uid == uid)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @classmethod
    async def get_multiple(
            cls,
            session: AsyncSession,
            uid: str | list | None = None,
    ) -> Sequence[Self]:
        if uid is None:
            stmt = (
                select(cls)
                .order_by(cls.uid.asc(),
                          cls.start_time.desc())
            )
            result = await session.execute(stmt)
            return result.scalars().all()

        if isinstance(uid, str):
            uid = [uid, ]
        stmt = (
            select(cls)
            .where(cls.uid.in_(uid))
            .order_by(cls.start_time.desc())
        )
        result = await session.execute(stmt)
        return result.scalars().all()

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
        )
        if system_uid:
            if isinstance(system_uid, str):
                system_uid = [system_uid, ]
            stmt = stmt.where(cls.system_uid.in_(system_uid))
        result = await session.execute(stmt)
        return result.scalars().all()

    @classmethod
    @cached(_cache_system_history, key=sessionless_hashkey)
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
        )
        if system_uid:
            if isinstance(system_uid, str):
                system_uid = [system_uid, ]
            stmt = stmt.where(cls.system_uid.in_(system_uid))
        result = await session.execute(stmt)
        return result.all()


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
    ) -> list[timed_value]:
        await cls.remove_expired(session)
        sub_stmt = (
            select(cls.id, sa_max(cls.timestamp))
            .group_by(cls.system_uid)
            .subquery()
        )
        stmt = select(
            cls.timestamp, cls.CPU_used, cls.CPU_temp, cls.RAM_process,
            cls.RAM_used, cls.DISK_used,
        ).join(sub_stmt, cls.id == sub_stmt.c.id)
        if system_uid:
            if isinstance(system_uid, str):
                system_uid = [system_uid, ]
            stmt = stmt.where(cls.system_uid.in_(system_uid))
        result = await session.execute(stmt)
        return result.all()
