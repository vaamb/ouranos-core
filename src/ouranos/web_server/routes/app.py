from fastapi import APIRouter, Depends, Query

from ouranos import current_app
from ouranos.core.database.models.app import FlashMessage, Service, ServiceLevel
from ouranos.web_server.dependencies import get_session
from ouranos.web_server.validate.response.app import (
    FlashMessageResponse, LoggingPeriodResponse, ServiceInfo)


router = APIRouter(
    prefix="/app",
    responses={404: {"description": "Not found"}},
    tags=["app"],
)


@router.get("/version")
async def get_version():
    return current_app.config["VERSION"]


@router.get("/logging_period", response_model=LoggingPeriodResponse)
async def get_logging_config():
    return {
        "weather": current_app.config["WEATHER_UPDATE_PERIOD"],
        "system": current_app.config["SYSTEM_LOGGING_PERIOD"],
        "sensors": current_app.config["SENSOR_LOGGING_PERIOD"],
    }


@router.get("/services", response_model=list[ServiceInfo])
async def get_services(
        level: ServiceLevel = Query(default=ServiceLevel.all),
        session=Depends(get_session)
):
    services = await Service.get_multiple(session=session, level=level)
    return services


@router.get("/flash_messages", response_model=list[FlashMessageResponse])
async def get_flash_messages(
        last: int = Query(default=10),
        session=Depends(get_session)
):
    msgs = await FlashMessage.get_multiple(session=session, max_first=last)
    return [msg.description for msg in msgs]
