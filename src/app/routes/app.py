from fastapi import APIRouter, Depends, Query

from src.app.dependencies import get_session
from src.app.utils import app_config
from src.core import api


router = APIRouter(
    prefix="/app",
    responses={404: {"description": "Not found"}},
    tags=["app"],
)


@router.get("/version")
async def get_version():
    return app_config.get("VERSION")


@router.get("/logging_period")
async def get_logging_config():
    return {
        "weather": app_config.get("OURANOS_WEATHER_UPDATE_PERIOD", None),
        "system": app_config.get("SYSTEM_LOGGING_PERIOD", None),
        "sensors": app_config.get("SENSORS_LOGGING_PERIOD", None),
    }


@router.get("/services")
async def get_services(level: str = Query(default="all"), session=Depends(get_session)):
    services = await api.service.get_multiple(session=session, level=level)
    return api.service.get_info(services)


# TODO: for future use
@router.get("/flash_messages")
async def get_flash_messages(session=Depends(get_session)):
    msgs = await api.flash_message.get_multiple(session=session)
    return api.flash_message.get_content(msgs)
