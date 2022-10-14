from fastapi import APIRouter, Depends, Query

from src.app.dependencies import get_session
from src.core import api
from src.core.g import config


router = APIRouter(
    prefix="/app",
    responses={404: {"description": "Not found"}},
    tags=["app"],
)


@router.get("/version")
async def get_version():
    return config.get("VERSION")


@router.get("/logging_period")
async def get_logging_config():
    return {
        "weather": config.get("WEATHER_UPDATE_PERIOD", None),
        "system": config.get("SYSTEM_LOGGING_PERIOD", None),
        "sensors": config.get("SENSORS_LOGGING_PERIOD", None),
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
