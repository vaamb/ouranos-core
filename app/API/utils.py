from datetime import datetime, timedelta, timezone

import cachetools.func


@cachetools.func.ttl_cache(maxsize=1, ttl=300)
def time_limits() -> dict:
    now_utc = datetime.now(timezone.utc)
    return {
        "recent": (now_utc - timedelta(hours=36)).replace(tzinfo=None),
        "sensors": (now_utc - timedelta(days=7)).replace(tzinfo=None),
        "health": (now_utc - timedelta(days=31)).replace(tzinfo=None),
        "warnings": (now_utc - timedelta(days=7)).replace(tzinfo=None),
    }


def get_service(service):
    from app.services import get_manager
    try:
        return get_manager().services[service]
    except AttributeError:
        raise RuntimeError(f"Services have not been started, cannot get "
                           f"{service} service")
    except KeyError:
        raise ValueError(f"{service} is not a valid service")


def get_weather_data():
    try:
        return get_service("weather").get_data()
    except RuntimeError:
        return {}
