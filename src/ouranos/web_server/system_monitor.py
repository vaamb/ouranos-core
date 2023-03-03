from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from logging import getLogger, Logger
import os
import psutil

from ouranos import current_app, db, scheduler
from ouranos.sdk import api
from ouranos.core.config.consts import START_TIME
from ouranos.core.utils import DispatcherFactory


current_process = psutil.Process(os.getpid())


class SystemMonitor:
    def __init__(self):
        self.logger: Logger = getLogger("ouranos.aggregator")
        self.dispatcher = DispatcherFactory.get("application")
        self._mutex = asyncio.Lock()
        self._stop_event = asyncio.Event()

    async def get_resources_data(self) -> None:
        update_period = current_app.config.get("SYSTEM_UPDATE_PERIOD")

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

        while not self._stop_event.is_set():
            mem = psutil.virtual_memory()
            mem_proc = current_process.memory_info()
            disk = psutil.disk_usage("/")
            _cache = {
                "timestamp": datetime.now(timezone.utc).replace(microsecond=0),
                "CPU_used": psutil.cpu_percent(),
                "RAM_total": round(mem[0]/(1024*1024*1024), 2),
                "RAM_used": round(mem[3]/(1024*1024*1024), 2),
                "RAM_process": round(mem_proc.rss/(1024*1024*1024), 2),
                "DISK_total": round(disk[0]/(1024*1024*1024), 2),
                "DISK_used": round(disk[1]/(1024*1024*1024), 2),
                "CPU_temp": get_temp(),
                "start_time": START_TIME,
            }
            async with self._mutex:
                api.system.update_current_data(_cache)
            await self.dispatcher.emit(
                "current_server_data",
                data=_cache,
                namespace="application",
            )
            await asyncio.sleep(update_period)

    async def log_resources_data(self) -> None:
        self.logger.debug("Logging system resources")
        async with db.scoped_session() as session:
            data = api.system.get_current_data()
            try:
                del data["start_time"]
            except KeyError:
                pass
            if data:
                await api.system.create_data_record(session, data)

    def start(self) -> None:
        update_period = current_app.config.get("SYSTEM_UPDATE_PERIOD")
        logging_period = current_app.config.get("SYSTEM_LOGGING_PERIOD")
        if update_period is not None:
            self._stop_event.clear()
            asyncio.ensure_future(self.get_resources_data())
            if logging_period is not None:
                scheduler.add_job(
                    self.log_resources_data,
                    "cron", minute=f"*/{logging_period}",
                    second=1 + update_period, misfire_grace_time=1*60,
                    id="system_monitoring"
                )

    def stop(self) -> None:
        async def safe_clear():
            async with self._mutex:
                api.system.clear_current_data()

        self._stop_event.set()
        scheduler.remove_job(job_id="system_monitoring")
        asyncio.ensure_future(safe_clear())
