from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ouranos.sdk import api
from ouranos.web_server.auth import is_authenticated
from ouranos.web_server.dependencies import get_session
from ouranos.web_server.routes.gaia import router


@router.get(
    "/warnings",
    dependencies=[Depends(is_authenticated)],
)
async def get_warnings(
        session: AsyncSession = Depends(get_session),
):
    response = await api.gaia.get_recent_warnings(session, limit=8)
    return response
