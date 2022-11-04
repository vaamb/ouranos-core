import logging
import re

from dispatcher import (
    configure_dispatcher, get_dispatcher, RegisterEventMixin
)

from ouranos.core.database.models import Engine, Service

from .archiver import Archiver
from .calendar import Calendar
from .daily_recap import DailyRecap
from .shared_resources import db, scheduler
from .sun_times import SunTimes
from .system_monitor import SystemMonitor
from .weather import Weather
from .webcam import Webcam


pattern = re.compile(r'(?<!^)(?=[A-Z])')

_SERVICES_TUPLE = (
    Archiver, Calendar, DailyRecap, SunTimes, SystemMonitor,
    Weather, Webcam
)

SERVICES = {
    pattern.sub('_', service.__name__).lower(): service
    for service in _SERVICES_TUPLE
}


def _init_dependencies(config_class) -> None:
    configure_dispatcher(config_class, silent=True)
    db.init(config_class)
    db.create_all()
    _log_services_available()
    scheduler.start()


class _servicesManager(RegisterEventMixin):
    def __init__(self, config_class) -> None:
        self.config = config_class
        self.logger = logging.getLogger(
            f"{self.config.APP_NAME.lower()}.services"
        )
        self.logger.debug(f"Initializing {self.config.APP_NAME} services ...")
        self.dispatcher = get_dispatcher("services", async_based=True)
        self.register_dispatcher_events(self.dispatcher)
        self.services = {}
        self._services_running = []
        self._launch_services()
        self._thread = None
        self.dispatcher.start()
        self.logger.info(f"{self.config.APP_NAME} services successfully initialized")

    def _launch_services(self) -> None:
        self.logger.info(f"Starting services ...")
        for service in SERVICES:
            if SERVICES[service].LEVEL == "base":
                self.start_service(service)
            else:
                with db.scoped_session() as session:
                    status = (
                        session.query(Service)
                            .filter_by(name=service)
                            .one()
                            .status
                    )
                    if status:
                        self.start_service(service)
        self.logger.debug("Services successfully started")

    def start_service(self, service: str) -> None:
        if not self.services.get(service, ""):
            try:
                self.services[service] = SERVICES[service](self)
            except Exception as e:
                self.logger.error(
                    f"{service} was not successfully initialized. "
                    f"ERROR msg: {e}"
                )
        try:
            self.services[service].start()
        except RuntimeError as e:
            self.logger.warning(
                f"Service {service} is already running"
            )
        except Exception as e:
            self.logger.error(
                f"{service} was not successfully started. "
                f"ERROR msg: {e}"
            )
        self._services_running.append(service)

    def stop_service(self, service: str) -> None:
        try:
            self.services[service].stop()
        except RuntimeError as e:
            self.logger.error(e)
        self._services_running.remove(service)

    @property
    def services_running(self) -> list:
        return self._services_running

    @property
    def services_available(self) -> list:
        return [service.NAME for service in SERVICES]

    def dispatch_start_service(self, sender_uid, *args):
        self.start_service(*args)

    def dispatch_stop_service(self, sender_uid, *args):
        self.stop_service(*args)


services_manager: _servicesManager = None


def _log_services_available() -> None:
    with db.scoped_session() as session:
        for service in SERVICES:
            if SERVICES[service].LEVEL in ("app", "user"):
                s = session.query(Service).filter_by(name=service).first()
                if s is None:
                    s = Service(name=service, level=SERVICES[service].LEVEL)
                session.add(s)
        session.commit()


def start(config_class) -> None:
    global services_manager
    if not services_manager:
        _init_dependencies(config_class)
        services_manager = _servicesManager(config_class)


def exit_gracefully() -> None:
    with db.scoped_session() as session:
        session.query(Engine).update(
            {Engine.connected: False})
        session.commit()
    scheduler.shutdown()


def get_manager() -> _servicesManager:
    return services_manager


if __name__ == '__main__':
    from config import Config
    start(Config)
