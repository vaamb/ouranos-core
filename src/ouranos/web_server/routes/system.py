from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy.ext.asyncio import AsyncSession

from ouranos.core.database.models.system import System
from ouranos.core.utils import timeWindow
from ouranos.web_server.auth import is_admin
from ouranos.web_server.dependencies import get_session, get_time_window
from ouranos.web_server.validate.system import (
    CurrentSystemData, HistoricSystemData, SystemInfo)


router = APIRouter(
    prefix="/system",
    responses={404: {"description": "Not found"}},
    tags=["system"],
    dependencies=[Depends(is_admin)],
)


async def system_or_abort(
        session: AsyncSession,
        uid: str,
) -> System:
    system = await System.get(session=session, uid=uid)
    if system:
        return system
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="No system(s) found"
    )


@router.get("", response_model=list[SystemInfo])
async def get_systems(
        session: AsyncSession = Depends(get_session),
):
    system = await System.get_multiple(session)
    return system


@router.get("/{system_uid}", response_model=SystemInfo)
async def get_system(
        system_uid: str = Path(description="A server uid"),
        session: AsyncSession = Depends(get_session),
):
    system = await system_or_abort(session, uid=system_uid)
    return system


@router.get("/{system_uid}/data/current", response_model=CurrentSystemData)
async def get_current_system_data(
        system_uid: str = Path(description="A server uid"),
        session: AsyncSession = Depends(get_session),
):
    system = await system_or_abort(session, uid=system_uid)
    response = {
        "uid": system.uid,
        "hostname": system.hostname,
        "values": await system.get_recent_timed_values(session),
        # order is added by the serializer
        "totals": {
            "DISK_total": system.DISK_total,
            "RAM_total": system.RAM_total,
        }
    }
    return response


@router.get("/{system_uid}/data/historic", response_model=HistoricSystemData)
async def get_historic_system_data(
        system_uid: str = Path(description="A server uid"),
        time_window: timeWindow = Depends(get_time_window(rounding=10, grace_time=60)),
        session: AsyncSession = Depends(get_session),
):
    system = await system_or_abort(session, uid=system_uid)
    response = {
        "uid": system.uid,
        "hostname": system.hostname,
        "span": (time_window.start, time_window.end),
        "values": await system.get_timed_values(session, time_window),
        # order is added by the serializer
        "totals": {
            "DISK_total": system.DISK_total,
            "RAM_total": system.RAM_total,
        }
    }
    return response
