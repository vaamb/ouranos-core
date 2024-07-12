import typing as t

from fastapi import HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from ouranos import db

from ouranos.core.utils import create_time_window, timeWindow


async def get_session() -> AsyncSession:
    async with db.scoped_session() as session:
        yield session


start_time_query = Query(
    default=None, description="ISO (8601) formatted datetime from which the "
                              "research will be done")

end_time_query = Query(
    default=None, description="ISO (8601) formatted datetime up to which the "
                              "research will be done")


def get_time_window_round_600(
        start_time: t.Optional[str] = start_time_query,
        end_time: t.Optional[str] = end_time_query,
) -> timeWindow:
    try:
        return create_time_window(
            start_time, end_time, window_length=7, rounding_base=10, grace_time=60)
    except ValueError:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="'start_time' and 'end_time' should be valid iso times"
        )


def get_time_window_round_60(
        start_time: t.Optional[str] = start_time_query,
        end_time: t.Optional[str] = end_time_query,
) -> timeWindow:
    try:
        return create_time_window(
            start_time, end_time, window_length=7, rounding_base=1, grace_time=10)
    except ValueError:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="'start_time' and 'end_time' should be valid iso times"
        )
