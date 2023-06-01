from datetime import datetime
from typing import Optional, Self, Sequence

from asyncache import cached
from cachetools import TTLCache
import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from ouranos.core.database.models.common import Base, BaseSystemRecord
from ouranos.core.database.models.utils import sessionless_hashkey
from ouranos.core.utils import timeWindow


_cache_system_history = TTLCache(maxsize=1, ttl=10)


# ---------------------------------------------------------------------------
#   System-related models, located in db_system
# ---------------------------------------------------------------------------
class System(Base):
    __tablename__ = "systems"
    __bind_key__ = "system"

    id: Mapped[int] = mapped_column(primary_key=True)
    uid: Mapped[str] = mapped_column()
    RAM_total: Mapped[float] = mapped_column(sa.Float(precision=2))
    DISK_total: Mapped[float] = mapped_column(sa.Float(precision=2))


class SystemRecord(BaseSystemRecord):
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
                cls.RAM_total, cls.RAM_used, cls.RAM_process, cls.DISK_total,
                cls.DISK_used
            )
            .where(
                (cls.timestamp > time_window.start) &
                (cls.timestamp <= time_window.end)
            )
        )
        result = await session.execute(stmt)
        return [r._data for r in result.all()]
