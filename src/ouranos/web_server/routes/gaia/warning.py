from fastapi import APIRouter, Body, Depends, Path, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from ouranos.core.database.models.gaia import GaiaWarning
from ouranos.web_server.auth import is_authenticated, is_operator
from ouranos.web_server.dependencies import get_session
from ouranos.web_server.validate.payload.common import WarningPayload
from ouranos.web_server.validate.response.base import ResultResponse, ResultStatus
from ouranos.web_server.validate.response.common import WarningResult


router = APIRouter(
    prefix="/warning",
    responses={404: {"description": "Not found"}},
    tags=["gaia/warning"],
)


@router.get("", response_model=list[WarningResult], dependencies=[Depends(is_authenticated)])
async def get_warnings(
        limit: int = Query(default=8, description="The number of warnings to fetch"),
        solved: bool = Query(default=False, description="Whether to retrieve solved warnings"),
        session: AsyncSession = Depends(get_session),
):
    response = await GaiaWarning.get_multiple(session, limit=limit, show_solved=solved)
    return response


@router.post("/u/",
             response_model=ResultResponse,
             status_code=status.HTTP_202_ACCEPTED,
             dependencies=[Depends(is_operator)])
async def create_warning(
        response: Response,
        payload: WarningPayload = Body(
            description="Information about the new warning"),
        session: AsyncSession = Depends(get_session),
):
    try:
        await GaiaWarning.create(session, payload.model_dump())
        return ResultResponse(
            msg=f"A new warning was successfully created",
            status=ResultStatus.success
        )
    except Exception as e:
        response.status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
        return ResultResponse(
            msg=f"Failed to create a new warning. Error msg: "
                f"`{e.__class__.__name__}: {e}`",
            status=ResultStatus.failure
        )


@router.put("/u/{id}",
            response_model=ResultResponse,
            status_code=status.HTTP_202_ACCEPTED,
            dependencies=[Depends(is_operator)])
async def update_warning(
        id: int = Path(description="The id of the warning message"),
        payload: WarningPayload = Body(
                    description="Updated information about the warning"),
        session: AsyncSession = Depends(get_session),
):
    await GaiaWarning.update(session, values=payload.model_dump(), id=id)
    return ResultResponse(
        msg=f"Updated warning with id '{id}'",
        status=ResultStatus.success
    )


@router.post("/u/{id}/mark_as_seen",
            response_model=ResultResponse,
            status_code=status.HTTP_202_ACCEPTED,
            dependencies=[Depends(is_authenticated)])
async def mark_warning_as_seen(
        id: int = Path(description="The id of the warning message"),
        session: AsyncSession = Depends(get_session),
):
    await GaiaWarning.mark_as_seen(session, id=id)
    return ResultResponse(
        msg=f"Warning with id '{id}' marked as seen",
        status=ResultStatus.success
    )


@router.post("/u/{id}/mark_as_solved",
            response_model=ResultResponse,
            status_code=status.HTTP_202_ACCEPTED,
            dependencies=[Depends(is_authenticated)])
async def mark_warning_as_solved(
        id: int = Path(description="The id of the warning message"),
        session: AsyncSession = Depends(get_session),
):
    await GaiaWarning.mark_as_solved(session, id=id)
    return ResultResponse(
        msg=f"Warning with id '{id}' marked as solved",
        status=ResultStatus.success
    )
