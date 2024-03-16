from fastapi import (
    APIRouter, Body, Depends, HTTPException, Path, Query, Response, status)
from sqlalchemy.ext.asyncio import AsyncSession

from ouranos.core.database.models.app import CalendarEvent, UserMixin
from ouranos.web_server.auth import get_current_user, is_authenticated
from ouranos.web_server.dependencies import get_session
from ouranos.web_server.validate.base import ResultResponse, ResultStatus
from ouranos.web_server.validate.calendar import (
    EventCreationPayload, EventUpdatePayload, EventInfo)


router = APIRouter(
    prefix="/calendar",
    responses={
        403: {"description": "Unauthorized"},
        404: {"description": "Not found"},
    },
    tags=["app/services/calendar"],
)


@router.get("",
            response_model=list[EventInfo],
            dependencies=[Depends(is_authenticated)])
async def get_events(
        limit: int = Query(default=8, description="The number of events to fetch"),
        session: AsyncSession = Depends(get_session),
):
    response = await CalendarEvent.get_multiple(session, limit=limit)
    return response


@router.post("/u",
             response_model=ResultResponse,
             status_code=status.HTTP_202_ACCEPTED,
             dependencies=[Depends(is_authenticated)])
async def create_event(
        response: Response,
        payload: EventCreationPayload = Body(
            description="Information about the new event"),
        current_user: UserMixin = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
):
    try:
        await CalendarEvent.create(
            session, creator_id=current_user.id, values=payload.model_dump())
        return ResultResponse(
            msg=f"A new event was successfully created",
            status=ResultStatus.success
        )
    except Exception as e:
        response.status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
        return ResultResponse(
            msg=f"Failed to create a new event. Error msg: "
                f"`{e.__class__.__name__}: {e}`",
            status=ResultStatus.failure
        )


@router.put("/u/{event_id}",
            response_model=ResultResponse,
            status_code=status.HTTP_202_ACCEPTED,
            dependencies=[Depends(is_authenticated)])
async def update_event(
        event_id: int = Path(description="The id of the event to update"),
        payload: EventUpdatePayload = Body(
                    description="Updated information about the event"),
        current_user: UserMixin = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
):
    event = await CalendarEvent.get(session, event_id=event_id)
    if event.created_by != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    values = {
        key: value for key, value in payload.model_dump().items()
        if value is not None
    }
    await CalendarEvent.update(session, event_id=event_id, values=values)
    return ResultResponse(
        msg=f"Updated event with id '{event_id}'",
        status=ResultStatus.success
    )


@router.post("/u/{event_id}/mark_as_inactive",
             response_model=ResultResponse,
             status_code=status.HTTP_202_ACCEPTED,
             dependencies=[Depends(is_authenticated)])
async def mark_event_as_inactive(
        event_id: int = Path(description="The id of the event to update"),
        current_user: UserMixin = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
):
    event = await CalendarEvent.get(session, event_id=event_id)
    if event.created_by != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    await CalendarEvent.inactivate(session, event_id=event_id)
    return ResultResponse(
        msg=f"Event with id '{event_id}' marked as inactive",
        status=ResultStatus.success
    )
