from collections import namedtuple
from datetime import datetime, timedelta, timezone

import cachetools.func


timeWindow = namedtuple("timeWindow", ("start", "end"))


def round_time_to_nearest_multiple(dt: datetime,
                                   rounding_base: int = 10,
                                   grace_time: int = 60) -> datetime:
    grace_time = timedelta(seconds=grace_time)
    rounded_minute = dt.minute // rounding_base * rounding_base
    return (dt.replace(minute=rounded_minute, second=0, microsecond=0)
            + grace_time)


def create_time_window(start: datetime = None,
                       end: datetime = None,
                       **kwargs
                       ) -> timeWindow:
    now = datetime.now(timezone.utc)
    if not start:
        start = now - timedelta(days=7)
    if not end:
        end = now
    return timeWindow(
        round_time_to_nearest_multiple(start, **kwargs),
        round_time_to_nearest_multiple(end, **kwargs)
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
