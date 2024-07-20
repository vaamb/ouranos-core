from typing import Optional

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


class get_time_window:  # noqa: 801
    def __init__(
            self,
            rounding: int,
            grace_time: int,
            window_length: int = 7
    ) -> None:
        self.rounding = rounding
        self.grace_time = grace_time
        self.window_length = window_length

    def __call__(
            self,
            start_time: Optional[str] = start_time_query,
            end_time: Optional[str] = end_time_query,
    ) -> timeWindow:
        try:
            return create_time_window(
                start_time, end_time, window_length=7, rounding_base=self.rounding,
                grace_time=self.grace_time)
        except ValueError as e:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(e)
            )
