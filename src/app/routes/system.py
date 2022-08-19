from fastapi import APIRouter, Depends

from src import api
from src.app.dependencies import get_session, get_time_window
from src.app.auth import is_admin


router = APIRouter(
    prefix="/system",
    responses={404: {"description": "Not found"}},
    tags=["system"],
)


@router.get("/current_data")
async def get_current_system_data(
        is_admin: bool = Depends(is_admin),
):
    response = api.admin.get_current_system_data()
    return response


@router.get("/data")
async def get_historic_system_data(
        is_admin: bool = Depends(is_admin),
        session=Depends(get_session),
        time_window=Depends(get_time_window),
):
    historic_system_data = api.admin.get_historic_system_data(
        session, time_window
    )
    return historic_system_data
