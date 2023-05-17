from __future__ import annotations

from pathlib import Path
import typing as t

from apscheduler.schedulers import (
    SchedulerAlreadyRunningError, SchedulerNotRunningError)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from sqlalchemy_wrapper import AsyncSQLAlchemyWrapper

from ouranos.core.config import (
    ConfigDict, get_base_dir, get_cache_dir, get_config, get_log_dir)
from ouranos.core.database.base import CustomMeta
from ouranos.core.utils import json


class _DynamicVar:
    def __getattribute__(self, item: str):
        attr = object.__getattribute__(self, item)
        if callable(attr):
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
        self.config: ConfigDict = get_config
        self.base_dir: Path = get_base_dir
        self.cache_dir: Path = get_cache_dir
        self.log_dir: Path = get_log_dir


current_app = _CurrentApp()
db: AsyncSQLAlchemyWrapper = AsyncSQLAlchemyWrapper(
    model=CustomMeta,
    engine_options={
        "json_serializer": json.dumps,
        "json_deserializer": json.loads,
    },
)
scheduler: AsyncIOScheduler = _SchedulerWrapper()
