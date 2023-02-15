from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ouranos.core.cache import get_cache
from ouranos.core.database.models.system import SystemHistory
from ouranos.sdk.api.utils import timeWindow


async def get_historic_data(
        session: AsyncSession,
        time_window: timeWindow
) -> dict:
    stmt = (
        select(SystemHistory)
        .where(
            (SystemHistory.timestamp > time_window.start) &
            (SystemHistory.timestamp <= time_window.end)
        )
        .with_entities(
            SystemHistory.timestamp, SystemHistory.CPU_used,
            SystemHistory.CPU_temp, SystemHistory.RAM_used,
            SystemHistory.RAM_total, SystemHistory.DISK_used,
            SystemHistory.DISK_total
        )
    )
    result = await session.execute(stmt)
    data = result.scalars().all()
    return {
        "data": data,
        "order": ["datetime", "CPU_used", "CPU_temp", "RAM_used",
                  "RAM_total", "DISK_used", "DISK_total"]
    }


async def create_data_record(
        session: AsyncSession,
        data_record: dict,
) -> SystemHistory:
    record = SystemHistory(**data_record)
    session.add(record)
    await session.commit()
    return record


def get_current_data() -> dict:
    cache = get_cache("system_data")
    return {**cache}


def update_current_data(data: dict) -> None:
    cache = get_cache("system_data")
    cache.update(data)


def clear_current_data(key: str | None = None) -> None:
    cache = get_cache("system_data")
    if key:
        del cache[key]
    else:
        cache.clear()
