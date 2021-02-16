import logging

from app import app_name
from app.database import out_of_Flask_app_db as db
from app.models import Service


class serviceTemplate:
    NAME = "serviceTemplate"
    LEVEL = "base"

    def __init__(self):
        self._logger = \
            logging.getLogger(f"{app_name}.services.{self.NAME.lower()}")
        self._service_name = f"{self.NAME.lower()}Service"
        self._logger.info(f"Initializing {self._service_name}")
        try:
            self._init()
            self._logger.debug(f"{self._service_name} was successfully "
                               f"initialized")
            self._started = False
        except Exception as e:
            self._logger.error(f"{self._service_name} was not successfully "
                               f"initialized. ERROR msg: {e}")
            raise e

    def _init(self):
        print(f"_init method was not overwritten for {self.NAME}")

    def _start(self):
        print(f"_start method was not overwritten for {self.NAME}")

    def _stop(self):
        print(f"_stop method was not overwritten for {self.NAME}")

    def start(self):
        if not self._started:
            try:
                self._start()
                if self.LEVEL in ("app", "user"):
                    with db.scoped_session() as session:
                        db_service = (session.query(Service)
                                      .filter_by(name=self.NAME)
                                      .one())
                        if not db_service.status:
                            db_service.status = 1
                            session.commit()
                self._started = True
                self._logger.debug(f"{self._service_name} "
                                   f"successfully started")
            except Exception as e:
                self._logger.error(
                    f"{self._service_name} was not "
                    f"successfully started. ERROR msg: {e}")
                raise e
        else:
            raise RuntimeError(f"{self._service_name} is "
                               f"already running ")

    def stop(self):
        if self._started:
            self._logger.info(f"Stopping {self._service_name}")
            try:
                self._stop()
                if self.LEVEL in ("app", "user"):
                    with db.scoped_session() as session:
                        db_service = (session.query(Service)
                                      .filter_by(name=self.NAME)
                                      .one())
                        if db_service.status:
                            db_service.status = 0
                            session.commit()
                self._started = False
                self._logger.debug(f"{self._service_name} "
                                   f"successfully stopped")
            except Exception as e:
                self._logger.error(
                    f"{self._service_name} was not "
                    f"successfully stopped. ERROR msg: {e}")
                raise e

    @property
    def status(self) -> bool:
        return self._started