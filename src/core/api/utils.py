from collections import namedtuple
from datetime import datetime, timedelta, timezone

import cachetools.func


timeWindow = namedtuple("timeWindow", ("start", "end"))


def round_datetime(
        dt: datetime,
        rounding_base: int = 10,
        grace_time: int = 60
) -> datetime:
    """ Round the datetime to the nearest 10 minutes to allow result caching
    """
    grace_time = timedelta(seconds=grace_time)
    rounded_minute = dt.minute // rounding_base * rounding_base
    return (
        dt.replace(minute=rounded_minute, second=0, microsecond=0) + grace_time
    )


def create_time_window(
        start: str = None,
        end: str = None,
        window_length: int = 7,
        **kwargs
) -> timeWindow:
    if end:
        _end = datetime.fromisoformat(end)
    else:
        _end = datetime.now(timezone.utc)
    if start:
        _start = datetime.fromisoformat(start)
    else:
        _start = _end - timedelta(days=window_length)
    if _start > _end:
        _start, _end = _end, _start
    return timeWindow(
        round_datetime(_start, **kwargs),
        round_datetime(_end, **kwargs)
    )


@cachetools.func.ttl_cache(maxsize=1, ttl=300)
# TODO: redesign
def time_limits() -> dict:
    now_utc = datetime.now(timezone.utc)
    return {
        "recent": (now_utc - timedelta(hours=36)).replace(tzinfo=None),
        "sensors": (now_utc - timedelta(days=7)).replace(tzinfo=None),
        "health": (now_utc - timedelta(days=31)).replace(tzinfo=None),
        "warnings": (now_utc - timedelta(days=7)).replace(tzinfo=None),
    }
