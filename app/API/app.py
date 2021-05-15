from app.API.utils import get_services_manager


def get_services_available() -> list:
    services_manager = get_services_manager()
    if services_manager:
        return services_manager.services_available
    return []


def get_services_running() -> list:
    services_manager = get_services_manager()
    if services_manager:
        return services_manager.services_running
    return []


def get_functionalities(summarized_ecosystems_info: dict) -> dict:
    app_functionalities = summarized_ecosystems_info
    app_functionalities["weather"] = True if "weather" in get_services_running() else False
    return app_functionalities
