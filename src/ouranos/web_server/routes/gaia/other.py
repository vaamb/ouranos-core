from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ouranos.core import validate
from ouranos.sdk import api
from ouranos.web_server.auth import get_current_user
from ouranos.web_server.dependencies import get_session
from ouranos.web_server.routes.gaia import router


@router.get("/warnings")
async def get_warnings(
        current_user: validate.app.user = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
):
    if current_user.is_authenticated:
        response = await api.gaia.get_recent_warnings(session, limit=8)
        return response
    raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access forbidden",
            )
