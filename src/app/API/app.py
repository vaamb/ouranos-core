import cachetools.func

from src.models import Service


_cache = {}


def get_services_available(session) -> list:
    try:
        return _cache["services"]
    except KeyError:
        services = session.query(Service).all()
        _cache["services"] = [service.name for service in services]
    return _cache["services"]


def get_services_running(session) -> list:
    @cachetools.func.ttl_cache(maxsize=1, ttl=60)
    def inner_func():
        services = session.query(Service).filter_by(status=True).all()
        return [service.name for service in services]
    return inner_func()


def get_functionalities(summarized_ecosystems_info: dict, session) -> dict:
    app_functionalities = summarized_ecosystems_info
    app_functionalities["weather"] = True \
        if "weather" in get_services_running(session) else False
    return app_functionalities
