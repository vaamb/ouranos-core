from __future__ import annotations

from pathlib import Path

from apscheduler.schedulers import (
    SchedulerAlreadyRunningError, SchedulerNotRunningError
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from ouranos.core.config import get_base_dir, get_config
from ouranos.core.config.consts import ImmutableDict
from .database.wrapper import AsyncSQLAlchemyWrapper


base_dir: Path
config: ImmutableDict[str, str | int | bool | dict[str, str]]


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


db: AsyncSQLAlchemyWrapper = AsyncSQLAlchemyWrapper()
scheduler: AsyncIOScheduler = _SchedulerWrapper()


def __getattr__(name):
    if name == "base_dir":
        return get_base_dir()
    elif name == "config":
        return get_config()
    else:
        return globals().get(name)  # TODO: fix issue with __path__
