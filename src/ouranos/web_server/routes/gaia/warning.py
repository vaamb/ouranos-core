from __future__ import annotations

from fastapi import APIRouter, Depends, Path, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from ouranos.core.database.models.app import UserMixin
from ouranos.core.database.models.gaia import GaiaWarning
from ouranos.web_server.auth import get_current_user, is_authenticated
from ouranos.web_server.dependencies import get_session
from ouranos.web_server.routes.gaia.utils import ecosystems_uid_q
from ouranos.web_server.validate.response.base import ResultResponse, ResultStatus
from ouranos.web_server.validate.warning import WarningResult


router = APIRouter(
    prefix="/warning",
    responses={404: {"description": "Not found"}},
    tags=["gaia/warning"],
)


@router.get("", response_model=list[WarningResult], dependencies=[Depends(is_authenticated)])
async def get_warnings(
        ecosystems_uid: list[str] | None = ecosystems_uid_q,
        solved: bool = Query(default=False, description="Whether to retrieve solved warnings"),
        limit: int = Query(default=8, description="The number of warnings to fetch"),
        session: AsyncSession = Depends(get_session),
):
    response = await GaiaWarning.get_multiple(
        session, limit=limit, ecosystems=ecosystems_uid, show_solved=solved)
    return response


@router.post("/u/{warning_id}/mark_as_seen",
             response_model=ResultResponse,
             status_code=status.HTTP_202_ACCEPTED,
             dependencies=[Depends(is_authenticated)])
async def mark_warning_as_seen(
        warning_id: int = Path(description="The id of the warning message"),
        current_user: UserMixin = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
):
    await GaiaWarning.mark_as_seen(
        session, warning_id=warning_id, user_id=current_user.id)
    return ResultResponse(
        msg=f"Warning with id '{warning_id}' marked as seen",
        status=ResultStatus.success
    )


@router.post("/u/{warning_id}/mark_as_solved",
             response_model=ResultResponse,
             status_code=status.HTTP_202_ACCEPTED,
             dependencies=[Depends(is_authenticated)])
async def mark_warning_as_solved(
        warning_id: int = Path(description="The id of the warning message"),
        current_user: UserMixin = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
):
    await GaiaWarning.mark_as_solved(
        session, warning_id=warning_id, user_id=current_user.id)
    return ResultResponse(
        msg=f"Warning with id '{warning_id}' marked as solved",
        status=ResultStatus.success
    )
