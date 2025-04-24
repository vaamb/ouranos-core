from datetime import datetime
from typing import Annotated

from fastapi import (
    APIRouter, Body, Depends, HTTPException, Path, Query, status)
from sqlalchemy.ext.asyncio import AsyncSession

from gaia_validators import safe_enum_from_name

from ouranos.core.database.models.app import (
    CalendarEvent, CalendarEventVisibility, Permission, ServiceName, UserMixin)
from ouranos.web_server.auth import get_current_user, is_authenticated
from ouranos.web_server.dependencies import get_session
from ouranos.web_server.routes.services.utils import service_enabled
from ouranos.web_server.routes.utils import http_datetime
from ouranos.web_server.validate.calendar import (
    EventCreationPayload, EventUpdatePayload, EventInfo)


router = APIRouter(
    prefix="/calendar",
    responses={
        403: {"description": "Unauthorized"},
        404: {"description": "Not found"},
    },
    dependencies=[
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
        visibility: Annotated[
            str | None,
            Query(description="Events' visibility level"),
        ] = CalendarEventVisibility.public.name,
        page: Annotated[int, Query()] = 1,
        per_page: Annotated[int, Query(le=100)] = 10,
        current_user: Annotated[UserMixin, Depends(get_current_user)],
        session: Annotated[AsyncSession, Depends(get_session)],
):
    start_time: datetime | None = http_datetime(start_time)
    end_time: datetime | None = http_datetime(end_time)
    visibility = safe_enum_from_name(CalendarEventVisibility, visibility)
    if current_user.can(Permission.ADMIN):
        # Admins can see all events
        response = await CalendarEvent.get_multiple(
            session, start_time=start_time, end_time=end_time, page=page,
            per_page=per_page, visibility=visibility)
    else:
        # Regular users can only see their own events at most
        response = await CalendarEvent.get_multiple_with_visibility(
            session, start_time=start_time, end_time=end_time, page=page,
            per_page=per_page, visibility=visibility, user_id=current_user.id)
    return response


@router.post("/u",
             status_code=status.HTTP_202_ACCEPTED,
             dependencies=[Depends(is_authenticated)])
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
        return "A new event was successfully created"
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Failed to create a new event. Error msg: "
                f"`{e.__class__.__name__}: {e}`"
            ),
        )


@router.put("/u/{event_id}",
            status_code=status.HTTP_202_ACCEPTED,
            dependencies=[Depends(is_authenticated)])
async def update_event(
        event_id: Annotated[int, Path(description="The id of the event to update")],
        payload: Annotated[
            EventUpdatePayload,
            Body(description="Updated information about the event"),
        ],
        current_user: Annotated[UserMixin, Depends(get_current_user)],
        session: Annotated[AsyncSession, Depends(get_session)],
):
    event = await CalendarEvent.get_with_visibility(session, event_id=event_id)
    if event.created_by != current_user.id and not current_user.can(Permission.ADMIN):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    values = payload.model_dump(exclude_defaults=True)
    try:
        await CalendarEvent.update(session, event_id=event_id, values=values)
        return f"Updated event '{event.title}'"
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Failed to update the event. Error msg: "
                f"`{e.__class__.__name__}: {e}`"
            ),
        )


@router.delete("/u/{event_id}",
               status_code=status.HTTP_202_ACCEPTED,
               dependencies=[Depends(is_authenticated)])
async def delete_event(
        event_id: Annotated[int, Path(description="The id of the event to update")],
        current_user: Annotated[UserMixin, Depends(get_current_user)],
        session: Annotated[AsyncSession, Depends(get_session)],
):
    event = await CalendarEvent.get_with_visibility(session, event_id=event_id)
    if event.created_by != current_user.id and not current_user.can(Permission.ADMIN):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    try:
        await CalendarEvent.inactivate(session, event_id=event_id)
        return f"Event '{event.title}' deleted"
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Failed to delete the event. Error msg: "
                f"`{e.__class__.__name__}: {e}`"
            ),
        )
