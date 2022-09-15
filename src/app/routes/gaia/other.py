from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from . import router
from src.app.auth import get_current_user
from src.app.dependencies import get_session
from src.core.pydantic.models.app import PydanticUserMixin
from src.core import api


@router.get("/warnings")
async def get_warnings(
        current_user: PydanticUserMixin = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
):
    if current_user.is_authenticated:
        response = await api.gaia.get_recent_warnings(session, limit=8)
        return response
    raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access forbidden",
            )
