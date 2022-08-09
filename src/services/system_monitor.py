from datetime import datetime, timezone
import os
import psutil
from threading import Thread, Event

from src.cache import systemData
from src.consts import START_TIME
from src.database.models.system import SystemHistory
from src.services.template import ServiceTemplate
from src.services.shared_resources import db, scheduler


SYSTEM_UPDATE_PERIOD = 5
current_process = psutil.Process(os.getpid())


# TODO: allow multiple serve to report system data (use an id before dict)
class SystemMonitor(ServiceTemplate):
    LEVEL = "base"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._data = systemData
        self._thread = None
        self._stopEvent = Event()

    def _loop(self) -> None:
        def try_get_temp():
            try:
                return round(psutil.sensors_temperatures()
                             .get("cpu_thermal")[0][1], 2)
            except (AttributeError, KeyError, TypeError):
                return None

        while True:
            _cache = {
                "datetime": datetime.now(timezone.utc).replace(microsecond=0),
                "CPU_used": psutil.cpu_percent(),
                "RAM_total": round(psutil.virtual_memory()[0]/(1024*1024*1024), 2),
                "RAM_used": round(psutil.virtual_memory()[3]/(1024*1024*1024), 2),
                "DISK_total": round(psutil.disk_usage("/")[0]/(1024*1024*1024), 2),
                "DISK_used": round(psutil.disk_usage("/")[1]/(1024*1024*1024), 2),
                "CPU_temp": try_get_temp(),
                "RAM_process": round(current_process.memory_info().rss/(1024*1024*1024), 2),
                "start_time": START_TIME,
            }
            with self.mutex:
                self._data.update(_cache)
            self.manager.dispatcher.emit("application", "current_server_data", data={**self._data})
            self._stopEvent.wait(SYSTEM_UPDATE_PERIOD)
            if self._stopEvent.is_set():
                break

    def _log_resources_data(self) -> None:
        self.logger.debug("Logging system resources")
        with db.scoped_session() as session:
            system = SystemHistory(
                datetime=self._data["datetime"],
                CPU_used=self._data["CPU_used"],
                CPU_temp=self._data.get("CPU_temp", None),
                RAM_total=self._data["RAM_total"],
                RAM_used=self._data["RAM_used"],
                DISK_total=self._data["DISK_total"],
                DISK_used=self._data["DISK_used"],
                # TODO: add RAM_process
            )
            session.add(system)
            session.commit()

    def _start(self) -> None:
        self._stopEvent.clear()
        self._thread = Thread(target=self._loop)
        self._thread.name = f"services-{SystemMonitor}"
        self._thread.start()
        scheduler.add_job(self._log_resources_data, "cron",
                          minute=f"*/{self.config.SYSTEM_LOGGING_PERIOD}",
                          second=1 + SYSTEM_UPDATE_PERIOD,
                          misfire_grace_time=1 * 60, id="system_monitoring")

    def _stop(self) -> None:
        self._data.clear()
        self._stopEvent.set()
        self._thread.join()
        self._thread = None

    @property
    def system_data(self) -> dict:
        return self._data
