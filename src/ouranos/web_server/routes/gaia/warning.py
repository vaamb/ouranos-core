from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ouranos.core.database.models.gaia import GaiaWarning
from ouranos.web_server.auth import is_authenticated
from ouranos.web_server.dependencies import get_session
from ouranos.web_server.validate.response.gaia import GaiaWarningResult


router = APIRouter(
    prefix="/warning",
    responses={404: {"description": "Not found"}},
    tags=["gaia/warning"],
)


@router.get("", response_model=list[GaiaWarningResult], dependencies=[Depends(is_authenticated)])
async def get_warnings(
        limit: int = Query(default=8, description="The number of warnings to fetch"),
        session: AsyncSession = Depends(get_session),
):
    response = await GaiaWarning.get_multiple(session, limit=limit)
    return response
