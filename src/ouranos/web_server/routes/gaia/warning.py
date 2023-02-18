from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ouranos.sdk import api
from ouranos.web_server.auth import is_authenticated
from ouranos.web_server.dependencies import get_session


router = APIRouter(
    prefix="/warning",
    responses={404: {"description": "Not found"}},
    tags=["gaia/warning"],
)


@router.get("/", dependencies=[Depends(is_authenticated)])
async def get_warnings(
        session: AsyncSession = Depends(get_session),
):
    response = await api.gaia.get_recent_warnings(session, limit=8)
    return response
