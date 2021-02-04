import logging

from app import app_name
from app.database import out_of_Flask_app_db as db
from app.models import Service
from app.services import calendar, daily_recap, sun_times, telegram_chat_bot,\
    weather, webcam


_base = {
    "sun_times": sun_times,
}

_app = {
    "weather": weather,
    "webcam": webcam,
    "calendar": calendar,
}

_user = {
    "daily_recap": daily_recap,
    "telegram_chat_bot": telegram_chat_bot,
}

_optional = {**_app, **_user}

_services = {**_base, **_optional}


def log_services_available():
    sapp = {s: "app" for s in _app}
    suser = {s: "user" for s in _user}
    services = {**sapp, **suser}
    with db.scoped_session() as session:
        for s in services:
            service = session.query(Service).filter_by(name=s).first()
            if service is None:
                service = Service(name=s, level=services[s])
            session.add(service)
        session.commit()


log_services_available()


class UnknownService(Exception):
    pass


def get(service_name: str):
    try:
        return _services[service_name]
    except KeyError:
        raise UnknownService(f"Service {service_name} is not available")


class servicesManager:
    def __init__(self):
        self.logger = logging.getLogger(f"{app_name}.services")
        self.logger.info("Initializing services module")
        self.started = []

        for service in _base:
            self.start(service_name=service)

        with db.scoped_session() as session:
            for service in _optional:
                status = (session.query(Service)
                          .filter_by(name=service)
                          .one()
                          .status)
                if status:
                    self.start(service_name=service)
        self.logger.debug("Service module has been initialized")

    def start(self, service_name: str) -> None:
        service = get(service_name=service_name)
        self.logger.debug(f"Starting {service_name} service")
        try:
            service.start()
            self.started.append(service_name)
        except Exception as e:
            print(f"Exception in {service_name}: {e}")
            return
        if service_name in _optional:
            with db.scoped_session() as session:
                db_service = (session.query(Service)
                              .filter_by(name=service_name)
                              .one())
                if not db_service.status:
                    db_service.status = 1
                    session.commit()

    def stop(self, service_name: str) -> None:
        service = get(service_name=service_name)
        self.logger.debug(f"Stopping {service_name} service")
        try:
            service.stop()
            service_index = self.started.index(service_name)
            del self.started[service_index]
        except Exception as e:
            print(e)
            return
        if service_name in _optional:
            with db.scoped_session() as session:
                db_service = (session.query(Service)
                            .filter_by(name=service_name)
                            .one())
                if db_service.status:
                    db_service.status = 0
                    session.commit()


services_manager = servicesManager()
