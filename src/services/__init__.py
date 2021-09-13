import logging

from src.app.models import engineManager, Service
from src import dataspace
from src.dataspace import get_dispatcher
from src.dataspace.dispatcher import registerEventMixin

from src.services.archiver import Archiver
from src.services.calendar import Calendar
from src.services.daily_recap import dailyRecap
from src.services.shared_resources import db, scheduler
from src.services.sun_times import sunTimes
from src.services.system_monitor import systemMonitor
from src.services.telegram_chat_bot import telegramChatbot
from src.services.weather import Weather
from src.services.webcam import Webcam


SERVICES = (Archiver, Calendar, dailyRecap, sunTimes, systemMonitor,
            telegramChatbot, Weather, Webcam)

_services = {"base": {}, "app": {}, "user": {}}
for SERVICE in SERVICES:
    _services[SERVICE.LEVEL][SERVICE.NAME] = SERVICE


def _init_dependencies(config_class) -> None:
    dataspace.init(config_class)
    db.init(config_class)
    _log_services_available()
    scheduler.start()


class _servicesManager(registerEventMixin):
    def __init__(self, config_class) -> None:
        self.config = config_class
        self.logger = logging.getLogger(f"{self.config.APP_NAME}.services")
        self.logger.info(f"Initializing {self.config.APP_NAME} services ...")
        self.dispatcher = get_dispatcher("services")
        self._register_dispatcher_events(self.dispatcher)
        self.dispatcher.start()
        self.services = {}
        self._services_running = []
        self._init_services()
        self._thread = None
        self.logger.info(f"{self.config.APP_NAME} services successfully initialized")

    def _init_services(self) -> None:
        for level in _services:
            for service in _services[level]:
                self.services[service] = _services[level][service](self)

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
        self.logger.debug("Service module has been initialized")

    def start_service(self, service: str, *args, **kwargs) -> None:
        try:
            self.services[service].start()
        except RuntimeError as e:
            self.logger.error(e)
        self._services_running.append(service)

    def stop_service(self, service: str, *args, **kwargs) -> None:
        try:
            self.services[service].stop()
        except RuntimeError as e:
            self.logger.error(e)
        index = self._services_running.index(service)
        del self._services_running[index]

    @property
    def services_running(self) -> list:
        return self._services_running

    @property
    def services_available(self) -> list:
        return [service.NAME for service in SERVICES]

    def dispatch_start_service(self, *args, **kwargs):
        self.start_service(*args)

    def dispatch_stop_service(self, *args, **kwargs):
        self.stop_service(*args)


services_manager: _servicesManager = None


def _log_services_available() -> None:
    with db.scoped_session() as session:
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


def get_manager() -> _servicesManager:
    return services_manager
