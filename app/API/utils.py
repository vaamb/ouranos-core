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


def service_manager():
    from app.services import get_manager
    return get_manager()


def get_service(service):
    try:
        return service_manager().services[service]
    except AttributeError:
        raise RuntimeError(f"Services have not been started, cannot get "
                           f"{service} service")
    except KeyError:
        raise ValueError(f"{service} is not a valid service")
