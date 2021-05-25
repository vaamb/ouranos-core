from datetime import datetime, timezone
import logging
import psutil
from threading import Thread, Event, Lock

from app import app_name, scheduler, sio, START_TIME
from app.database import out_of_Flask_data_db as db
from app.models import System
from app.services.template import serviceTemplate
from config import Config


lock = Lock()

SYSTEM_UPDATE_PERIOD = 2

collector = logging.getLogger(f"{app_name}.collector")


class systemMonitor(serviceTemplate):
    NAME = "system_monitor"
    LEVEL = "base"

    def _init(self) -> None:
        self._data = {}
        self._thread = None
        self._stopEvent = Event()

    def _loop(self) -> None:
        while True:
            _cache = {
                "datetime": datetime.now(timezone.utc).replace(microsecond=0),
                "CPU_used": psutil.cpu_percent(),
                "RAM_total": round(psutil.virtual_memory()[0]/(1024*1024*1024), 2),
                "RAM_used": round(psutil.virtual_memory()[3]/(1024*1024*1024), 2),
                "DISK_total": round(psutil.disk_usage("/")[0]/(1024*1024*1024), 2),
                "DISK_used": round(psutil.disk_usage("/")[1]/(1024*1024*1024), 2)
            }
            try:
                _cache["CPU_temp"] = round(psutil.sensors_temperatures()
                                                 .get("cpu_thermal")[0][1], 2)
            except (AttributeError, KeyError):
                _cache["CPU_temp"] = 0

            with lock:
                self._data = _cache
            self._data["start_time"] = START_TIME
            try:
                sio.emit("current_server_data", self._data, namespace="/admin")
            except AttributeError as e:
                # Discard error when SocketIO has not started yet
                if "NoneType" not in e.args[0]:
                    raise e
            self._stopEvent.wait(SYSTEM_UPDATE_PERIOD)
            if self._stopEvent.isSet():
                break

    def _log_resources_data(self) -> None:
        collector.debug("Logging system resources")
        system = System(
            datetime=self._data["datetime"],
            CPU_used=self._data["CPU_used"],
            CPU_temp=self._data.get("CPU_temp", None),
            RAM_total=self._data["RAM_total"],
            RAM_used=self._data["RAM_used"],
            DISK_total=self._data["DISK_total"],
            DISK_used=self._data["DISK_used"],
        )
        db.session.add(system)
        db.session.commit()
        db.close_scope()

    def _start(self) -> None:
        self._stopEvent.clear()
        self._thread = Thread(target=self._loop)
        self._thread.name = f"services-{systemMonitor}"
        self._thread.start()
        scheduler.add_job(self._log_resources_data, "cron",
                          minute=f"*/{Config.SYSTEM_LOGGING_PERIOD}",
                          second=1 + SYSTEM_UPDATE_PERIOD,
                          misfire_grace_time=1 * 60, id="system_monitoring")

    def _stop(self) -> None:
        self._stopEvent.set()
        self._thread.join()
        self._thread = None

    @property
    def system_data(self) -> dict:
        return self._data
