from collections import namedtuple
from datetime import datetime, timedelta, timezone

import cachetools.func

from config import Config


timeWindow = namedtuple("timeWindow", ("start", "end"))


def create_time_window(start: datetime = None, end: datetime = None):
    def round_time(dt: datetime) -> datetime:
        dt = dt.replace(second=0, microsecond=0)
        minutes = dt.minute
        if minutes % Config.SENSORS_LOGGING_PERIOD == 1:
            return dt
        minutes = (minutes // Config.SENSORS_LOGGING_PERIOD
                   * Config.SENSORS_LOGGING_PERIOD) + 1
        return dt.replace(minute=minutes)

    @cachetools.func.ttl_cache(maxsize=1, ttl=60)
    # Make sure windows are the same in a given request
    def limit():
        return round_time(
            (datetime.now(timezone.utc) - timedelta(days=7))
                .replace(tzinfo=None)
        )

    if start:
        start_ = round_time(start)
    else:
        start_ = limit()

    if end:
        end_ = round_time(end)
    else:
        end_ = round_time(datetime.now().replace(tzinfo=None))

    return timeWindow(start_, end_)


@cachetools.func.ttl_cache(maxsize=1, ttl=300)
def time_limits() -> dict:
    now_utc = datetime.now(timezone.utc)
    return {
        "recent": (now_utc - timedelta(hours=36)).replace(tzinfo=None),
        "sensors": (now_utc - timedelta(days=7)).replace(tzinfo=None),
        "health": (now_utc - timedelta(days=31)).replace(tzinfo=None),
        "warnings": (now_utc - timedelta(days=7)).replace(tzinfo=None),
    }
