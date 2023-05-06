from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from logging import getLogger, Logger
import os
import psutil
import time as ctime

from ouranos import current_app, db
from ouranos.core.config.consts import START_TIME
from ouranos.core.database.models.memory import SystemDbCache
from ouranos.core.database.models.system import SystemRecord
from ouranos.core.utils import DispatcherFactory


current_process = psutil.Process(os.getpid())


try:
    psutil.sensors_temperatures().get("cpu_thermal")[0][1]
except (AttributeError, KeyError, TypeError):
    def get_temp() -> float | None:
        return None
else:
    def get_temp() -> float | None:
        return round(
            psutil.sensors_temperatures().get("cpu_thermal")[0][1], 2
        )


class SystemMonitor:
    def __init__(self):
        self.logger: Logger = getLogger("ouranos.aggregator")
        self.dispatcher = DispatcherFactory.get("application")
        self._mutex = asyncio.Lock()
        self._stop_event = asyncio.Event()

    async def loop(self) -> None:
        update_period = current_app.config.get("SYSTEM_UPDATE_PERIOD")
        logging_period = current_app.config.get("SYSTEM_LOGGING_PERIOD")
        logged = False

        while not self._stop_event.is_set():
            start = ctime.time()
            mem = psutil.virtual_memory()
            mem_proc = current_process.memory_info()
            disk = psutil.disk_usage("/")
            data = {
                "timestamp": datetime.now(timezone.utc),
                "CPU_used": psutil.cpu_percent(),
                "RAM_total": round(mem[0]/(1024*1024*1024), 2),
                "RAM_used": round(mem[3]/(1024*1024*1024), 2),
                "RAM_process": round(mem_proc.rss/(1024*1024*1024), 2),
                "DISK_total": round(disk[0]/(1024*1024*1024), 2),
                "DISK_used": round(disk[1]/(1024*1024*1024), 2),
                "CPU_temp": get_temp(),
            }
            await self.dispatcher.emit(
                "current_server_data",
                data={**data, "start_time": START_TIME},
                namespace="application",
            )
            async with db.scoped_session() as session:
                await SystemDbCache.insert_data(session, data)
            if logging_period and datetime.now().minute % logging_period == 0:
                if not logged:
                    async with db.scoped_session() as session:
                        self.logger.debug("Logging system resources")
                        await SystemRecord.create_records(session, data)
                logged = True
            else:
                logged = False
            time_for_loop = ctime.time() - start
            await asyncio.sleep(update_period-time_for_loop)

    def start(self) -> None:
        update_period = current_app.config.get("SYSTEM_UPDATE_PERIOD")
        if update_period is not None:
            self._stop_event.clear()
            asyncio.ensure_future(self.loop())

    def stop(self) -> None:
        async def safe_clear():
            async with db.scoped_session() as session:
                await SystemDbCache.clear(session)

        self._stop_event.set()
        asyncio.ensure_future(safe_clear())
