from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ouranos.core.config import consts
from ouranos.core.database.models.memory import SystemDbCache
from ouranos.core.database.models.system import SystemRecord
from ouranos.core.utils import timeWindow
from ouranos.web_server.auth import is_admin
from ouranos.web_server.dependencies import get_session, get_time_window
from ouranos.web_server.routes.utils import empty_result
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


@router.get("/data/current", response_model=list[SystemRecordResponse])
async def get_current_system_data(
        session: AsyncSession = Depends(get_session),
):
    return await SystemDbCache.get_recent(session)


@router.get("/data/historic", response_model=list[SystemRecordResponse])
async def get_historic_system_data(
        time_window: timeWindow = Depends(get_time_window),
        session: AsyncSession = Depends(get_session),
):
    historic_system_data = await SystemRecord.get_records(
        session, time_window)
    if historic_system_data:
        return {
            "records": [
                (record.timestamp, record.CPU_used, record.CPU_temp,
                 record.RAM_used, record.RAM_total, record.DISK_used,
                 record.DISK_total)
                for record in historic_system_data
            ],
            "order": ["timestamp", "CPU_used", "CPU_temp", "RAM_used",
                      "RAM_total", "DISK_used", "DISK_total"]
        }
    return empty_result([])
