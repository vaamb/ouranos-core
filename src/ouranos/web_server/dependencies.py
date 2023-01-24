import typing as t

from fastapi import HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from ouranos import db
from ouranos.sdk.api.utils import create_time_window, timeWindow


async def get_session() -> AsyncSession:
    async with db.scoped_session() as session:
        yield session


def get_time_window(
        start_time: t.Optional[str] = Query(default=None),
        end_time: t.Optional[str] = Query(default=None)
) -> timeWindow:
    try:
        return create_time_window(start_time, end_time)
    except ValueError:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="'start_time' and 'end_time' should be valid iso times"
        )
