from __future__ import annotations

import asyncio
from asyncio import Event, Task
from datetime import datetime, timezone
from logging import getLogger, Logger
import os
import psutil
import time as ctime

from ouranos import current_app, db
from ouranos.core.config.consts import START_TIME
from ouranos.core.database.models.system import (
    System, SystemDataCache, SystemDataRecord)
from ouranos.core.dispatchers import DispatcherFactory


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
        self.dispatcher = DispatcherFactory.get("application-internal")
        self._stop_event: Event = Event()
        self._task: Task | None = None

    @property
    def task(self) -> Task:
        if self._task is None:
            raise AttributeError("SystemMonitor task has not been set up")
        else:
            return self._task

    @task.setter
    def task(self, task: Task | None):
        self._task = task

    async def loop(self) -> None:
        update_period = current_app.config.get("SYSTEM_UPDATE_PERIOD")
        logging_period = current_app.config.get("SYSTEM_LOGGING_PERIOD")
        logged = False

        while not self._stop_event.is_set():
            start = ctime.time()
            uid = current_app.config["API_UID"]
            mem = psutil.virtual_memory()
            mem_proc = current_process.memory_info()
            disk = psutil.disk_usage("/")
            common_data = {
                "timestamp": datetime.now(timezone.utc),
                "CPU_used": psutil.cpu_percent(),
                "CPU_temp": get_temp(),
                "RAM_used": round(mem[3]/(1024*1024*1024), 2),
                "RAM_process": round(mem_proc.rss/(1024*1024*1024), 2),
                "DISK_used": round(disk[1]/(1024*1024*1024), 2),
            }
            await self.dispatcher.emit(
                "current_server_data",
                data={"uid": uid, **common_data},
                namespace="application-internal",
            )
            async with db.scoped_session() as session:
                await SystemDataCache.insert_data(
                    session, {"system_uid": uid, **common_data})
            if logging_period and datetime.now().minute % logging_period == 0:
                if not logged:
                    async with db.scoped_session() as session:
                        self.logger.debug("Logging system resources")
                        await SystemDataRecord.create_multiple(
                            session, {"system_uid": uid, **common_data})
                logged = True
            else:
                logged = False
            time_for_loop = ctime.time() - start
            await asyncio.sleep(update_period-time_for_loop)

    async def start(self) -> None:
        async with db.scoped_session() as session:
            await System.update_or_create(
                session,
                uid=current_app.config["API_UID"],
                values={
                    "hostname": current_app.config["API_HOST"],
                    "start_time": START_TIME,
                    "RAM_total": round(psutil.virtual_memory()[0]/(1024*1024*1024), 2),
                    "DISK_total": round(psutil.disk_usage("/")[0]/(1024*1024*1024), 2),
                }
            )

        update_period = current_app.config.get("SYSTEM_UPDATE_PERIOD")
        if update_period is not None:
            self._stop_event.clear()
            self.task = asyncio.ensure_future(self.loop())

    async def stop(self) -> None:
        self._stop_event.set()
        self.task.cancel()
        self.task = None
        async with db.scoped_session() as session:
            await SystemDataCache.clear(session)
