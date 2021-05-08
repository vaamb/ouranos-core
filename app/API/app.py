from app.API.utils import service_manager


def get_services_available() -> list:
    manager = service_manager()
    if manager:
        return manager.services_available
    return []


def get_services_running() -> list:
    manager = service_manager()
    if manager:
        return manager.services_running
    return []


def get_functionalities(summarized_ecosystems_info: dict) -> dict:
    app_functionalities = summarized_ecosystems_info
    app_functionalities["weather"] = True if "weather" in get_services_running() else False
    return app_functionalities
