from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ouranos.core.database.models.app import Service, ServiceLevel
from ouranos.web_server.dependencies import get_session
from ouranos.web_server.validate.app import ServiceInfo
from ouranos.web_server.routes.services.calendar import router as calendar_router
from ouranos.web_server.routes.services.weather import router as weather_router
from ouranos.web_server.routes.services.wiki import router as wiki_router


router = APIRouter(
    prefix="/app/services",
    responses={404: {"description": "Not found"}},
)


@router.get("", response_model=list[ServiceInfo])
async def get_services(
        *,
        level: Annotated[
            ServiceLevel | None,
            Query(description="The level of the services to fetch"),
        ] = None,
        session: Annotated[AsyncSession, Depends(get_session)],
):
    if level == ServiceLevel.all:
        level = None
    services = await Service.get_multiple(session, level=level)
    return services


router.include_router(calendar_router)
router.include_router(weather_router)
router.include_router(wiki_router)
