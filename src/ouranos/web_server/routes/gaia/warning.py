from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from ouranos.core.database.models.app import UserMixin
from ouranos.core.database.models.gaia import GaiaWarning
from ouranos.web_server.auth import get_current_user, is_authenticated
from ouranos.web_server.dependencies import get_session
from ouranos.web_server.routes.gaia.utils import eids_desc
from ouranos.web_server.validate.gaia.warning import WarningInfo


router = APIRouter(
    prefix="/warning",
    responses={404: {"description": "Not found"}},
    tags=["gaia/warning"],
)


@router.get("",
            response_model=list[WarningInfo],
            dependencies=[Depends(is_authenticated)])
async def get_warnings(
        *,
        ecosystems_uid: Annotated[list[str] | None, Query(description=eids_desc)] = None,
        solved: Annotated[
            bool,
            Query(description="Whether to retrieve solved warnings"),
        ] = False,
        limit: Annotated[int, Query(description="The number of warnings to fetch")] = 8,
        session: Annotated[AsyncSession, Depends(get_session)],
):
    response = await GaiaWarning.get_multiple(
        session, ecosystems=ecosystems_uid, show_solved=solved, limit=limit)
    return response


@router.post("/u/{warning_id}/mark_as_seen",
             status_code=status.HTTP_202_ACCEPTED,
             dependencies=[Depends(is_authenticated)])
async def mark_warning_as_seen(
        warning_id: Annotated[int, Path(description="The id of the warning message")],
        current_user: Annotated[UserMixin, Depends(get_current_user)],
        session: Annotated[AsyncSession, Depends(get_session)],
):
    await GaiaWarning.mark_as_seen(
        session, warning_id=warning_id, user_id=current_user.id)
    return f"Warning with id '{warning_id}' marked as seen"


@router.post("/u/{warning_id}/mark_as_solved",
             status_code=status.HTTP_202_ACCEPTED,
             dependencies=[Depends(is_authenticated)])
async def mark_warning_as_solved(
        warning_id: Annotated[int, Path(description="The id of the warning message")],
        current_user: Annotated[UserMixin, Depends(get_current_user)],
        session: Annotated[AsyncSession, Depends(get_session)],
):
    await GaiaWarning.mark_as_solved(
        session, warning_id=warning_id, user_id=current_user.id)
    return f"Warning with id '{warning_id}' marked as solved"
