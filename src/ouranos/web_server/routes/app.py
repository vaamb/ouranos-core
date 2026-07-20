from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ouranos import current_app
from ouranos.core.database.models.app import FlashMessage
from ouranos.web_server.dependencies import get_session
from ouranos.web_server.validate.app import (
    Contracts, FlashMessageInfo, LoggingPeriodInfo)


router = APIRouter(
    prefix="/app",
    responses={404: {"description": "Not found"}},
    tags=["app"],
)


@router.get("/version", response_model=str)
async def get_version():
    return current_app.config["VERSION"]


@router.get("/contracts", response_model=Contracts)
async def get_version():
    return {
        "gaia": current_app.config["GAIA_CONTRACT"],
        "rest": current_app.config["REST_CONTRACT"],
        "socketio": current_app.config["SOCKETIO_CONTRACT"],
    }


@router.get("/logging_period", response_model=LoggingPeriodInfo)
async def get_logging_config():
    return {
        "weather": current_app.config["WEATHER_UPDATE_PERIOD"],
        "system": current_app.config["SYSTEM_LOGGING_PERIOD"],
        "sensors": current_app.config["SENSOR_LOGGING_PERIOD"],
    }


@router.get("/flash_messages", response_model=list[FlashMessageInfo])
async def get_flash_messages(
        *,
        last: Annotated[int, Query(description="The number of messages to fetch")] = 10,
        session: Annotated[AsyncSession, Depends(get_session)],
):
    msgs = await FlashMessage.get_lasts(session=session, limit=last)
    return [msg.description for msg in msgs]
