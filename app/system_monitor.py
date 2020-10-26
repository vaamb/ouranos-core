import logging
import psutil
from datetime import datetime, timezone
from threading import Thread, Event

SYSTEM_UPDATE_FREQUENCY = 5


class systemMonitor:
    def __init__(self):
        self._data = {}
        self.thread = None
        self.stopEvent = Event()
        self.started = False

    def _loop(self):
        while True:
            _cache = {
                "datetime": datetime.now(timezone.utc).replace(microsecond=0),
                "CPU": psutil.cpu_percent(),
                "RAM_total": round(psutil.virtual_memory()[0] / (1024 * 1024 * 1024), 2),
                "RAM_used": round(psutil.virtual_memory()[3] / (1024 * 1024 * 1024), 2),
                "DISK_total": round(psutil.disk_usage("/")[0] / (1024 * 1024 * 1024), 2),
                "DISK_used": round(psutil.disk_usage("/")[1] / (1024 * 1024 * 1024), 2)
            }
            try:
                _cache["CPU_temp"] = (psutil.sensors_temperatures()
                                      .get("cpu-thermal", {})
                                      .get(0, {}).get(1))
            except AttributeError:
                pass
            self._data = _cache
            self.stopEvent.wait(5)
            if self.stopEvent.isSet():
                break

    def start(self):
        if not self.started:
            self.stopEvent.clear()
            self.thread = Thread(target=self._loop)
            self.thread.start()
            self.started = True
        else:
            raise RuntimeError

    def stop(self):
        if self.started:
            self.stopEvent.set()
            self.thread.join()
            self.thread = None
            self.started = False

    def status(self):
        return self.started

    @property
    def system_data(self):
        return self._data


# ---------------------------------------------------------------------------
#   System resources usage monitor
# ---------------------------------------------------------------------------
def log_resources_data():
    data = systemMonitor.system_data
    if data["datetime"].minute % Config.SYSTEM_LOGGING_FREQUENCY == 0:
        system = System(
            datetime=data["datetime"],
            CPU_used=data["CPU"],
            CPU_temp=data.get("CPU_temp", None),
            RAM_total=data["RAM_total"],
            RAM_used=data["RAM_used"],
            DISK_total=data["DISK_total"],
            DISK_used=data["DISK_used"],
        )
        db.session.add(system)
        db.session.commit()
