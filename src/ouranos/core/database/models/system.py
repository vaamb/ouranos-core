from datetime import datetime
from typing import Optional, Self, Sequence

from asyncache import cached
from cachetools import TTLCache
import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from ouranos.core.database.models.common import Base, Record
from ouranos.core.database.models.utils import sessionless_hashkey
from ouranos.core.utils import timeWindow


_cache_system_history = TTLCache(maxsize=1, ttl=10)


# ---------------------------------------------------------------------------
#   System-related models, located in db_system
# ---------------------------------------------------------------------------
class SystemHistory(Base, Record):
    __tablename__ = "system_history"
    __bind_key__ = "system"

    id: Mapped[int] = mapped_column(primary_key=True)
    system_uid: Mapped[str] = mapped_column()
    timestamp: Mapped[datetime] = mapped_column()
    CPU_used: Mapped[float] = mapped_column(sa.Float(precision=1))
    CPU_temp: Mapped[Optional[float]] = mapped_column(sa.Float(precision=1))
    RAM_total: Mapped[float] = mapped_column(sa.Float(precision=2))
    RAM_used: Mapped[float] = mapped_column(sa.Float(precision=2))
    RAM_process: Mapped[float] = mapped_column(sa.Float(precision=2))
    DISK_total: Mapped[float] = mapped_column(sa.Float(precision=2))
    DISK_used: Mapped[float] = mapped_column(sa.Float(precision=2))

    @classmethod
    @cached(_cache_system_history, key=sessionless_hashkey)
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
