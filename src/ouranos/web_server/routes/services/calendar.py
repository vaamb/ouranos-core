from datetime import datetime
from typing import Annotated

from fastapi import (
    APIRouter, Body, Depends, HTTPException, Path, Query, status)
from sqlalchemy.ext.asyncio import AsyncSession

from ouranos.core.database.models.app import (
    CalendarEvent, Permission, ServiceName, UserMixin)
from ouranos.web_server.auth import get_current_user, is_authenticated
from ouranos.web_server.dependencies import get_session
from ouranos.web_server.routes.services.utils import service_enabled
from ouranos.web_server.validate.base import ResultResponse, ResultStatus
from ouranos.web_server.validate.calendar import (
    EventCreationPayload, EventUpdatePayload, EventInfo)


router = APIRouter(
    prefix="/calendar",
    responses={
        403: {"description": "Unauthorized"},
        404: {"description": "Not found"},
    },
    dependencies=[
        Depends(is_authenticated),
        Depends(service_enabled(ServiceName.calendar)),
    ],
    tags=["app/services/calendar"],
)


@router.get("", response_model=list[EventInfo])
async def get_events(
        *,
        start_time: Annotated[
            str | None,
            Query(description="Lower bound as ISO (8601) formatted datetime"),
        ] = None,
        end_time: Annotated[
            str | None,
            Query(description="Upper bound as ISO (8601) formatted datetime"),
        ] = None,
        limit: Annotated[int, Query(description="The number of events to fetch")] = 10,
        session: Annotated[AsyncSession, Depends(get_session)],
):
    if isinstance(start_time, str):
        start_time = datetime.fromisoformat(start_time)
    if isinstance(end_time, str):
        end_time = datetime.fromisoformat(end_time)
    response = await CalendarEvent.get_multiple(
        session, start_time=start_time, end_time=end_time, limit=limit)
    return response


@router.post("/u",
             response_model=ResultResponse,
             status_code=status.HTTP_202_ACCEPTED)
async def create_event(
        payload: Annotated[
            EventCreationPayload,
            Body(description="Information about the new event"),
        ],
        current_user: Annotated[UserMixin, Depends(get_current_user)],
        session: Annotated[AsyncSession, Depends(get_session)],
):
    try:
        await CalendarEvent.create(
            session, creator_id=current_user.id, values=payload.model_dump())
        return ResultResponse(
            msg=f"A new event was successfully created",
            status=ResultStatus.success
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Failed to create a new event. Error msg: "
                f"`{e.__class__.__name__}: {e}`"
            ),
        )


@router.put("/u/{event_id}",
            response_model=ResultResponse,
            status_code=status.HTTP_202_ACCEPTED)
async def update_event(
        event_id: Annotated[int, Path(description="The id of the event to update")],
        payload: Annotated[
            EventUpdatePayload,
            Body(description="Updated information about the event"),
        ],
        current_user: Annotated[UserMixin, Depends(get_current_user)],
        session: Annotated[AsyncSession, Depends(get_session)],
):
    event = await CalendarEvent.get(session, event_id=event_id)
    if event.created_by != current_user.id and not current_user.can(Permission.ADMIN):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    values = payload.model_dump()
    await CalendarEvent.update(session, event_id=event_id, values=values)
    return ResultResponse(
        msg=f"Updated event with id '{event_id}'",
        status=ResultStatus.success
    )


@router.delete("/u/{event_id}",
               response_model=ResultResponse,
               status_code=status.HTTP_202_ACCEPTED)
async def delete_event(
        event_id: Annotated[int, Path(description="The id of the event to update")],
        current_user: Annotated[UserMixin, Depends(get_current_user)],
        session: Annotated[AsyncSession, Depends(get_session)],
):
    event = await CalendarEvent.get(session, event_id=event_id)
    if event.created_by != current_user.id and not current_user.can(Permission.ADMIN):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    await CalendarEvent.inactivate(session, event_id=event_id)
    return ResultResponse(
        msg=f"Event with id '{event_id}' deleted",
        status=ResultStatus.success
    )
