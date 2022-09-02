from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.cache import systemData
from src.core.api.utils import timeWindow
from src.core.database.models.system import SystemHistory


async def get_historic_system_data(
        session: AsyncSession,
        time_window: timeWindow
) -> dict:
    stmt = (
        select(SystemHistory)
        .where(
            (SystemHistory.datetime > time_window.start) &
            (SystemHistory.datetime <= time_window.end)
        )
        .with_entities(
            SystemHistory.datetime, SystemHistory.CPU_used,
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


async def create_system_data_record(
        session: AsyncSession,
        data_record: dict,
) -> SystemHistory:
    record = SystemHistory(**data_record)
    session.add(record)
    await session.commit()
    return record


def get_current_system_data():
    return {**systemData}


def update_current_system_data(data: dict):
    systemData.update(data)


def delete_current_system_data_key(key: str):
    del systemData[key]


def clear_current_system_data():
    systemData.clear()
