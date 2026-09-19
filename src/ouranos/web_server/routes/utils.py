from datetime import datetime

from fastapi import HTTPException, status


def http_datetime(datetime_str: str | None) -> datetime | None:
    if datetime_str is None:
        return None
    try:
        return datetime.fromisoformat(datetime_str)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Dates should be entered in a valid ISO (8601) format.",
        )
