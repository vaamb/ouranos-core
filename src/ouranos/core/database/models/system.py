from typing import Self, Sequence

from asyncache import cached
from cachetools import TTLCache
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ouranos.core.database.models.common import BaseSystemRecord
from ouranos.core.database.models.utils import sessionless_hashkey
from ouranos.core.utils import timeWindow


_cache_system_history = TTLCache(maxsize=1, ttl=10)


# ---------------------------------------------------------------------------
#   System-related models, located in db_system
# ---------------------------------------------------------------------------
class SystemRecord(BaseSystemRecord):
    __tablename__ = "system_records"
    __bind_key__ = "system"

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
