from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src import api
from src.api.utils import timeWindow
from src.app.dependencies import get_session, get_time_window
from src.app.auth import is_admin


router = APIRouter(
    prefix="/system",
    responses={404: {"description": "Not found"}},
    tags=["system"],
)


@router.get("/current_data", dependencies=[Depends(is_admin)])
async def get_current_system_data():
    response = api.admin.get_current_system_data()
    return response


@router.get("/data", dependencies=[Depends(is_admin)])
async def get_historic_system_data(
        session: Session = Depends(get_session),
        time_window: timeWindow = Depends(get_time_window),
):
    historic_system_data = api.admin.get_historic_system_data(
        session, time_window
    )
    return historic_system_data
