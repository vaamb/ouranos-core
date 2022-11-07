from __future__ import annotations

from inspect import isfunction

from apscheduler.schedulers import (
    SchedulerAlreadyRunningError, SchedulerNotRunningError
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from ouranos.core.config import get_base_dir, get_config
from .database.wrapper import AsyncSQLAlchemyWrapper


class _DynamicVar:
    def __getattribute__(self, item: str):
        attr = object.__getattribute__(self, item)
        if isfunction(attr):
            return attr()
        return attr


class _SchedulerWrapper(AsyncIOScheduler):
    def start(self, paused=False):
        try:
            super().start(paused)
        except SchedulerAlreadyRunningError:
            pass

    def shutdown(self, wait=True):
        try:
            super().shutdown(wait)
        except SchedulerNotRunningError:
            pass


current_app = _DynamicVar()
current_app.base_dir = get_base_dir
current_app.config = get_config

db: AsyncSQLAlchemyWrapper = AsyncSQLAlchemyWrapper()
scheduler: AsyncIOScheduler = _SchedulerWrapper()
