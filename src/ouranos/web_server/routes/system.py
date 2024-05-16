from fastapi import APIRouter, Depends, Path
from sqlalchemy.ext.asyncio import AsyncSession

from ouranos.core.database.models.system import System
from ouranos.core.utils import timeWindow
from ouranos.web_server.auth import is_admin
from ouranos.web_server.dependencies import get_session, get_time_window
from ouranos.web_server.validate.system import SystemData, SystemInfo


router = APIRouter(
    prefix="/system",
    responses={404: {"description": "Not found"}},
    tags=["system"],
    dependencies=[Depends(is_admin)],
)


@router.get("", response_model=list[SystemInfo])
async def get_systems(
        session: AsyncSession = Depends(get_session),
):
    system = await System.get_multiple(session)
    return system


@router.get("/{server_uid}", response_model=SystemInfo)
async def get_system(
        server_uid: str = Path(description="A server uid"),
        session: AsyncSession = Depends(get_session),
):
    system = await System.get(session, uid=server_uid)
    return system


@router.get("/{server_uid}/data/current", response_model=SystemData)
async def get_current_system_data(
        server_uid: str = Path(description="A server uid"),
        session: AsyncSession = Depends(get_session),
):
    system = await System.get(session, uid=server_uid)
    return {
        "values": await system.get_recent_timed_values(session),
        "totals": {
            "DISK_TOTAL": system.DISK_total,
            "RAM_TOTAL": system.RAM_total,
        }
    }


@router.get("/{server_uid}/data/historic", response_model=SystemData)
async def get_historic_system_data(
        server_uid: str = Path(description="A server uid"),
        time_window: timeWindow = Depends(get_time_window),
        session: AsyncSession = Depends(get_session),
):
    system = await System.get(session, uid=server_uid)
    return {
        "values": await system.get_timed_values(session, time_window),
        "totals": {
            "DISK_TOTAL": system.DISK_total,
            "RAM_TOTAL": system.RAM_total,
        }
    }
