from fastapi import APIRouter, Depends, HTTPException, Query, status

from src import api
from src.app import app_config
from src.app.auth import get_current_user
from src.app.dependencies import get_session
from src.app.pydantic.models.app import PydanticUserMixin


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
    response = api.app.get_services(session=session, level=level)
    return response


# TODO: for future use
@router.get("/flash_message")
async def get_flash_message():
    response = {}
    return response


@router.get("/warnings")
async def get_warnings(
        current_user: PydanticUserMixin = Depends(get_current_user),
        session=Depends(get_session)
):
    if current_user.is_authenticated:
        response = api.warnings.get_recent_warnings(session, limit=8)
        return response
    raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access forbidden",
            )
