from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

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


@router.get("/current_data", dependencies=[Depends(is_admin)])
async def get_current_system_data() -> dict:
    response = api.system.get_current_data()
    return response


@router.get("/data", dependencies=[Depends(is_admin)])
async def get_historic_system_data(
        time_window: timeWindow = Depends(get_time_window),
        session: AsyncSession = Depends(get_session),
) -> dict:
    historic_system_data = await api.system.get_historic_data(
        session, time_window
    )
    if historic_system_data:
        return historic_system_data
    return empty_result({})
