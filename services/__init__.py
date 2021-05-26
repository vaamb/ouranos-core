import logging

from services.database import db
from app.models import engineManager, Service
import dataspace

from services.calendar import Calendar
from services.daily_recap import dailyRecap
from services.sun_times import sunTimes
from services.system_monitor import systemMonitor
from services.telegram_chat_bot import telegramChatbot
from services.shared_resources import scheduler
from services.weather import Weather
from services.webcam import Webcam


# TODO: add a background task which listens to a queue to start and stop services


SERVICES = (Calendar, dailyRecap, sunTimes, systemMonitor, telegramChatbot,
            Weather, Webcam)

_services = {"base": {}, "app": {}, "user": {}}
for SERVICE in SERVICES:
    _services[SERVICE.LEVEL][SERVICE.NAME] = SERVICE


services_manager = None


class _servicesManager:
    def __init__(self, config_class) -> None:
        self.config = config_class
        self.logger = logging.getLogger(f"{self.config.APP_NAME}.services")
        self.logger.info(f"Initializing {self.config.APP_NAME} services ...")
        self.event_dispatcher = dataspace.sio_queue
        self.services = {}
        self._services_running = []
        self._init_services()
        self.logger.info(f"{self.config.APP_NAME} services successfully initialized")

    def _init_services(self) -> None:
        for level in _services:
            for service in _services[level]:
                self.services[service] = _services[level][service](self)

        for service in _services["base"]:
            self.services[service].start()
            self._services_running.append(service)

        with db.scoped_session("app") as session:
            for level in ("app", "user"):
                for service in _services[level]:
                    status = (session.query(Service).filter_by(name=service)
                                     .one().status)
                    if status:
                        self.services[service].start()
                        self._services_running.append(service)
        self.logger.debug("Service module has been initialized")

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


def _init_dependencies(config_class) -> None:
    dataspace.init(config_class)
    db.init(config_class=config_class)
    _log_services_available()
    scheduler.start()


def _log_services_available() -> None:
    with db.scoped_session("app") as session:
        for level in ("app", "user"):
            for s in _services[level]:
                service = session.query(Service).filter_by(name=s).first()
                if service is None:
                    service = Service(name=s, level=level)
                session.add(service)
        session.commit()


def start(config_class) -> None:
    global services_manager
    if not services_manager:
        _init_dependencies(config_class)
        services_manager = _servicesManager(config_class)


def exit_gracefully() -> None:
    with db.scoped_session() as session:
        session.query(engineManager).update(
            {engineManager.connected: False})
        session.commit()
    scheduler.shutdown()


def get_manager():
    return services_manager
