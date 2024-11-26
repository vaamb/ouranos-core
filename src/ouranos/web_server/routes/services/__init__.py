from typing import Annotated

from fastapi import APIRouter, Body, Depends, Path, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from dispatcher import AsyncDispatcher

from ouranos.core.database.models.app import Service, ServiceLevel, ServiceName
from ouranos.core.dispatchers import DispatcherFactory
from ouranos.web_server.dependencies import get_session
from ouranos.web_server.validate.app import ServiceInfo, ServiceUpdatePayload
from ouranos.web_server.validate.base import ResultResponse, ResultStatus


router = APIRouter(
    prefix="/app/services",
    responses={404: {"description": "Not found"}},
)


@router.get("", response_model=list[ServiceInfo], tags=["/app/services"])
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


@router.put("/u/{service_name}",
            status_code=status.HTTP_202_ACCEPTED,
            response_model=ResultResponse,
            tags=["/app/services"])
async def update_service(
        *,
        service_name: Annotated[
            ServiceName,
            Path(description="The name of the service to update"),
        ],
        payload: Annotated[
            ServiceUpdatePayload,
            Body(description="Updated service status"),
        ],
        session: Annotated[AsyncSession, Depends(get_session)],
):
    service_status = payload.model_dump()["status"]
    await Service.update(
        session, name=service_name, values={"status": service_status})
    # TODO: catch the dispatched message in the aggregator and act accordingly
    dispatcher: AsyncDispatcher = DispatcherFactory.get("application-internal")
    await dispatcher.emit(
        event="update_service",
        data={"name": service_name, "status": service_status},
        namespace="aggregator-internal",
    )
    return ResultResponse(
        msg=f"Updated service '{service_name.name}' to status '{service_status}'",
        status=ResultStatus.success
    )


from ouranos.web_server.routes.services.calendar import router as calendar_router
from ouranos.web_server.routes.services.weather import router as weather_router
from ouranos.web_server.routes.services.wiki import router as wiki_router

router.include_router(calendar_router)
router.include_router(weather_router)
router.include_router(wiki_router)
