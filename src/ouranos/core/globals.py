from __future__ import annotations

from inspect import isfunction
from pathlib import Path
import typing as t

from apscheduler.schedulers import (
    SchedulerAlreadyRunningError, SchedulerNotRunningError
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from ouranos.core.config import (
    get_base_dir, get_cache_dir, get_config, get_log_dir
)
from .database.wrapper import AsyncSQLAlchemyWrapper


if t.TYPE_CHECKING:
    from ouranos.core.config import config_type


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


class _CurrentApp(_DynamicVar):
    def __init__(self):
        self.config: "config_type" = get_config
        self.base_dir: Path = get_base_dir
        self.cache_dir: Path = get_cache_dir
        self.log_dir: Path = get_log_dir


current_app = _CurrentApp()
db: AsyncSQLAlchemyWrapper = AsyncSQLAlchemyWrapper()
scheduler: AsyncIOScheduler = _SchedulerWrapper()
