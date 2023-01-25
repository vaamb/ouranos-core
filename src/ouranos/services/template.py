import logging
import re
import threading
import weakref

from dispatcher import RegisterEventMixin

from ouranos.core.database.models import Service


pattern = re.compile(r'(?<!^)(?=[A-Z])')


class ServiceTemplate(RegisterEventMixin):
    LEVEL = "base"

    def __init__(self, manager):
        self.manager = weakref.proxy(manager)
        self.config = self.manager.config
        self.mutex = threading.Lock()
        self._service_name = pattern.sub('_', self.__class__.__name__).lower()
        self.logger = logging.getLogger(
            f"{self.config.APP_NAME.lower()}.services.{self._service_name}"
        )
        self.logger.debug(f"Initializing {self._service_name}")
        self.register_dispatcher_events(self.manager.dispatcher)
        self._started = False

    def _finish_init(self):
        self.logger.debug("Initialization successfully")

    def _start(self):
        raise NotImplementedError(
            "This method must be implemented in a subclass"
        )

    def _stop(self):
        raise NotImplementedError(
            "This method must be implemented in a subclass"
        )

    def start(self):
        if not self._started:
            self._start()
            if self.LEVEL in ("app", "user"):
                with db.scoped_session() as session:
                    db_service = (session.query(Service)
                                  .filter_by(name=self._service_name)
                                  .one())
                    if not db_service.status:
                        db_service.status = 1
                        session.commit()
            self._started = True
            self.logger.debug(
                f"{self._service_name.replace('_', ' ').capitalize()} service started"
            )
        else:
            raise RuntimeError(
                f"{self._service_name} is already running"
            )

    def stop(self):
        if self._started:
            self.logger.debug(f"Stopping {self._service_name}")
            try:
                self._stop()
                if self.LEVEL in ("app", "user"):
                    with db.scoped_session() as session:
                        db_service = (
                            session.query(Service)
                                .filter_by(name=self._service_name)
                                .one()
                        )
                        if db_service.status:
                            db_service.status = 0
                            session.commit()
                self._started = False
                self.logger.debug(f"{self._service_name} stopped")
            except Exception as e:
                self.logger.error(
                    f"{self._service_name} was not "
                    f"successfully stopped. ERROR msg: {e}")
                raise e

    @property
    def status(self) -> bool:
        return self._started
