from fastapi import APIRouter, Depends, Query

from ouranos.api.dependencies import get_session
from ouranos import current_app, sdk


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
        "weather": current_app.config.get("WEATHER_UPDATE_PERIOD", None),
        "system": current_app.config.get("SYSTEM_LOGGING_PERIOD", None),
        "sensors": current_app.config.get("SENSORS_LOGGING_PERIOD", None),
    }


@router.get("/services")
async def get_services(level: str = Query(default="all"), session=Depends(get_session)):
    services = await sdk.service.get_multiple(session=session, level=level)
    return sdk.service.get_info(services)


# TODO: for future use
@router.get("/flash_messages")
async def get_flash_messages(session=Depends(get_session)):
    msgs = await sdk.flash_message.get_multiple(session=session)
    return sdk.flash_message.get_content(msgs)
