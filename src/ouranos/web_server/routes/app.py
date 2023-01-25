from fastapi import APIRouter, Depends, Query

from ouranos import current_app
from ouranos.sdk import api
from ouranos.web_server.dependencies import get_session


router = APIRouter(
    prefix="/app",
    responses={404: {"description": "Not found"}},
    tags=["app"],
)


@router.get("/version")
async def get_version():
    return current_app.config["VERSION"]


@router.get("/logging_period")
async def get_logging_config():
    return {
        "weather": current_app.config.get["WEATHER_UPDATE_PERIOD"],
        "system": current_app.config["SYSTEM_LOGGING_PERIOD"],
        "sensors": current_app.config["SENSOR_LOGGING_PERIOD"],
    }


@router.get("/services")
async def get_services(level: str = Query(default="all"), session=Depends(get_session)):
    services = await api.service.get_multiple(session=session, level=level)
    return api.service.get_info(services)


@router.get("/flash_messages")
async def get_flash_messages(session=Depends(get_session)):
    msgs = await api.flash_message.get_multiple(session=session)
    return api.flash_message.get_content(msgs)
