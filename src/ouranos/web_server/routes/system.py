from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ouranos.core.config import consts
from ouranos.core.database.models.memory import SystemDbCache
from ouranos.core.database.models.system import SystemRecord
from ouranos.core.utils import timeWindow
from ouranos.web_server.auth import is_admin
from ouranos.web_server.dependencies import get_session, get_time_window
from ouranos.web_server.validate.response.system import SystemRecordResponse


router = APIRouter(
    prefix="/system",
    responses={404: {"description": "Not found"}},
    tags=["system"],
    dependencies=[Depends(is_admin)],
)


@router.get("/start_time",)
async def get_current_system_data() -> int:
    return consts.START_TIME


@router.get("/data/current", response_model=SystemRecordResponse)
async def get_current_system_data(
        session: AsyncSession = Depends(get_session),
):
    return {
        "values": await SystemDbCache.get_recent_timed_values(session),
        "order": ["timestamp", "system_uid", "CPU_used", "CPU_temp",
                  "RAM_used", "RAM_total", "RAM_process", "DISK_used",
                  "DISK_total"]
    }


@router.get("/data/historic", response_model=SystemRecordResponse)
async def get_historic_system_data(
        time_window: timeWindow = Depends(get_time_window),
        session: AsyncSession = Depends(get_session),
):
    return {
        "values": await SystemRecord.get_timed_values(
            session, time_window),
        "order": ["timestamp", "system_uid", "CPU_used", "CPU_temp",
                  "RAM_used", "RAM_total", "RAM_process", "DISK_used",
                  "DISK_total"]
    }
