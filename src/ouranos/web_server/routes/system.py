from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ouranos.core import validate
from ouranos.core.config import consts
from ouranos.sdk import api
from ouranos.sdk.api.utils import timeWindow
from ouranos.web_server.auth import is_admin
from ouranos.web_server.dependencies import get_session, get_time_window
from ouranos.web_server.routes.utils import empty_result


router = APIRouter(
    prefix="/system",
    responses={404: {"description": "Not found"}},
    tags=["system"],
)


@router.get(
    "/start_time",
    dependencies=[Depends(is_admin)],
)
async def get_current_system_data() -> int:
    return consts.START_TIME


@router.get(
    "/current_data",
    response_model=validate.system.system_record,
    dependencies=[Depends(is_admin)],
)
async def get_current_system_data() -> dict:
    return api.system.get_current_data()


@router.get(
    "/data",
    response_model=list[validate.system.system_record],
    dependencies=[Depends(is_admin)],
)
async def get_historic_system_data(
        time_window: timeWindow = Depends(get_time_window),
        session: AsyncSession = Depends(get_session),
):
    historic_system_data = await api.system.get_historic_data(
        session, time_window
    )
    if historic_system_data:
        return historic_system_data
    return empty_result({})
