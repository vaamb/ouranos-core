import typing as t

from fastapi import HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from . import db
from src.core import api


async def get_session() -> AsyncSession:
    async with db.scoped_session() as session:
        yield session


def get_time_window(
        start_time: t.Optional[str] = Query(default=None),
        end_time: t.Optional[str] = Query(default=None)
) -> api.utils.timeWindow:
    try:
        return api.utils.create_time_window(start_time, end_time)
    except ValueError:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="'start_time' and 'end_time' should be valid iso times"
        )
