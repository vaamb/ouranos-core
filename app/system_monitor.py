from datetime import datetime, timezone
import logging
import psutil
from threading import Thread, Event

from app import app_name, scheduler
from app.database import out_of_Flask_data_db as db
from app.models import System
from config import Config

# TODO: move into services
SYSTEM_UPDATE_FREQUENCY = 5

collector = logging.getLogger(f"{app_name}.collector")


class systemMonitor:
    def __init__(self):
        self._data = {}
        self.thread = None
        self.stopEvent = Event()
        self.started = False

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
                pass
            self._data = _cache
            self.stopEvent.wait(5)
            if self.stopEvent.isSet():
                break

    def start(self) -> None:
        if not self.started:
            self.stopEvent.clear()
            self.thread = Thread(target=self._loop)
            self.thread.start()
            self.started = True
        else:
            raise RuntimeError

    def stop(self) -> None:
        if self.started:
            self.stopEvent.set()
            self.thread.join()
            self.thread = None
            self.started = False

    @property
    def status(self) -> bool:
        return self.started

    @property
    def system_data(self) -> dict:
        return self._data


systemMonitor = systemMonitor()
systemMonitor.start()


# ---------------------------------------------------------------------------
#   System resources usage monitor
# ---------------------------------------------------------------------------
@scheduler.scheduled_job(id="log_resources_data", trigger="cron",
                         minute=f"*/{Config.SYSTEM_LOGGING_FREQUENCY}",
                         second=1+SYSTEM_UPDATE_FREQUENCY,
                         misfire_grace_time=1*60)
def log_resources_data() -> None:
    collector.debug("Logging system resources")
    data = systemMonitor.system_data
    system = System(
        datetime=data["datetime"],
        CPU_used=data["CPU_used"],
        CPU_temp=data.get("CPU_temp", None),
        RAM_total=data["RAM_total"],
        RAM_used=data["RAM_used"],
        DISK_total=data["DISK_total"],
        DISK_used=data["DISK_used"],
    )

    db.session.add(system)
    db.session.commit()
    db.close_scope()
