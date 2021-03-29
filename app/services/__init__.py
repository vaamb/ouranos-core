import logging

from app import app_name
from app.database import out_of_Flask_app_db as db
from app.models import Service
from app.services.calendar import Calendar
from app.services.daily_recap import dailyRecap
from app.services.sun_times import sunTimes
from app.services.system_monitor import systemMonitor
from app.services.telegram_chat_bot import telegramChatbot
from app.services.weather import Weather
from app.services.webcam import Webcam


SERVICES = (Calendar, dailyRecap, sunTimes, systemMonitor, telegramChatbot,
            Weather, Webcam)

_services = {"base": {}, "app": {}, "user": {}}
for SERVICE in SERVICES:
    _services[SERVICE.LEVEL][SERVICE.NAME] = SERVICE


logger = logging.getLogger(f"{app_name}.services")

services_manager = None


def log_services_available() -> None:
    with db.scoped_session() as session:
        for level in ("app", "user"):
            for s in _services[level]:
                service = session.query(Service).filter_by(name=s).first()
                if service is None:
                    service = Service(name=s, level=level)
                session.add(service)
        session.commit()


class _servicesManager:
    def __init__(self) -> None:
        logger.info(f"Initializing {app_name} services ...")
        log_services_available()
        self.services = {}
        self._services_running = []
        self._init_services()
        logger.info(f"{app_name} services successfully initialized")

    def _init_services(self) -> None:
        for level in _services:
            for service in _services[level]:
                self.services[service] = _services[level][service]()

        for service in _services["base"]:
            self.services[service].start()
            self._services_running.append(service)

        with db.scoped_session() as session:
            for level in ("app", "user"):
                for service in _services[level]:
                    status = (session.query(Service).filter_by(name=service)
                                     .one().status)
                    if status:
                        self.services[service].start()
                        self._services_running.append(service)
        logger.debug("Service module has been initialized")

    def start_service(self, service: str) -> None:
        self.services[service].start()
        self._services_running.append(service)

    def stop_service(self, service: str) -> None:
        self.services[service].stop()
        index = self._services_running.index(service)
        del self._services_running[index]

    @property
    def services_running(self) -> list:
        return self._services_running

    @property
    def services_available(self) -> list:
        return [service.NAME for service in SERVICES]


def start() -> None:
    global services_manager
    if not services_manager:
        services_manager = _servicesManager()


def get_manager():
    if not services_manager:
        start()
    return services_manager
