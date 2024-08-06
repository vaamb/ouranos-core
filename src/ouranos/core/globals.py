from __future__ import annotations

from logging import getLogger, Logger
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.schedulers.base import STATE_STOPPED

from sqlalchemy_wrapper import AsyncSQLAlchemyWrapper

from ouranos.core.config import (
    ConfigDict, get_base_dir, get_cache_dir, get_config, get_log_dir)
from ouranos.core.database.base import CustomMeta, custom_metadata
from ouranos.core.utils import json


logger: Logger = getLogger(f"ouranos")


class _DynamicVar:
    def __getattribute__(self, item: str):
        attr = object.__getattribute__(self, item)
        if callable(attr):
            return attr()
        return attr


class _SchedulerWrapper(AsyncIOScheduler):
    def start(self, paused=False):
        if self.state == STATE_STOPPED:
            logger.info("Starting the scheduler")
            super().start(paused)

    def shutdown(self, wait=True):
        if self.state != STATE_STOPPED:
            logger.info("Stopping the scheduler")
            super().shutdown(wait)


class _CurrentApp(_DynamicVar):
    def __init__(self):
        self.config: ConfigDict = get_config
        self.base_dir: Path = get_base_dir
        self.cache_dir: Path = get_cache_dir
        self.log_dir: Path = get_log_dir


current_app = _CurrentApp()
db: AsyncSQLAlchemyWrapper = AsyncSQLAlchemyWrapper(
    model=CustomMeta,
    metadata=custom_metadata,
    engine_options={
        "json_serializer": json.dumps,
        "json_deserializer": json.loads,
    },
    session_options={
        "expire_on_commit": False,
    }
)
scheduler: AsyncIOScheduler = _SchedulerWrapper()
