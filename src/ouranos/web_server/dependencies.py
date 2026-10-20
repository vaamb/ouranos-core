from datetime import datetime, timezone
from typing import AsyncGenerator, Optional

from fastapi import HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from ouranos import db

from ouranos.core.database.models.utils import TimeWindow
from ouranos.core.utils import create_time_window


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with db.scoped_session() as session:
        yield session


def dt_query_text(start: bool) -> str:
    return (
        f"ISO (8601) formatted datetime {'from' if start else 'up to'} which the "
        f"research will be done. If no timezone is given, UTC is assumed."
    )


start_time_query = Query(default=None, description=dt_query_text(start=True))

end_time_query = Query(
    default=None, description=f"{dt_query_text(start=False)} By default, it is now.")

window_length_query = Query(
    default=7, description="The number of days to fetch if no start time is "
                           "provided.")


def http_datetime(datetime_str: str | None) -> datetime | None:
    if datetime_str is None:
        return None
    try:
        datetime_obj = datetime.fromisoformat(datetime_str)
        if datetime_obj.tzinfo is None:
            datetime_obj = datetime_obj.replace(tzinfo=timezone.utc)
        return datetime_obj
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Dates should be entered in a valid ISO (8601) format.",
        )


class get_time_window:  # noqa: N801
    def __init__(
            self,
            rounding: int,
            grace_time: int,
            default_window_length: int = 7,
            max_window_length: int | None = 7,
    ) -> None:
        self.rounding = rounding
        self.grace_time = grace_time
        self.default_window_length = default_window_length
        self.max_window_length = max_window_length

    def __call__(
            self,
            start_time: Optional[str] = start_time_query,
            end_time: Optional[str] = end_time_query,
            window_length: Optional[int] | None = window_length_query,
    ) -> TimeWindow:
        try:
            start_dt = http_datetime(start_time)
            end_dt = http_datetime(end_time)
            return create_time_window(
                start_dt, end_dt, rounding_base=self.rounding,
                grace_time=self.grace_time, max_window_length=self.max_window_length,
                window_length=window_length or self.default_window_length)
        except ValueError as e:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=str(e)
            )
