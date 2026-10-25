from __future__ import annotations

from logging import Logger

from ouranos import db as ouranos_db, scheduler
from ouranos.core.config import ConfigDict
from ouranos.core.database.init import setup_db, tear_up_db


class _CommonResourcesState:
    def __init__(self):
        self.used_by: int = 0

    @property
    def initialized(self) -> bool:
        return self.used_by > 0

    def register(self) -> None:
        self.used_by += 1

    def unregister(self) -> None:
        if self.used_by <= 0:
            raise RuntimeError("There are no more registered resources")
        self.used_by -= 1


_common_resources_state = _CommonResourcesState()


def get_common_resources_state() -> _CommonResourcesState:
    return _common_resources_state


async def _init_the_scheduler(logger: Logger) -> None:
    logger.info("Initializing the scheduler")
    scheduler.start()
    logger.debug("Scheduler initialized")


async def acquire_common_resources(config: ConfigDict, logger: Logger) -> None:
    """Take a reference on the resources shared within the process (the
    database and the scheduler), initializing them on the first reference."""
    if not _common_resources_state.initialized:
        await setup_db(ouranos_db, config, logger)
        await _init_the_scheduler(logger)

    _common_resources_state.register()


async def release_common_resources() -> None:
    """Release a reference on the shared resources, clearing them when the
    last one is released."""
    _common_resources_state.unregister()
    # If nothing is using the common resources, clear them
    if _common_resources_state.used_by == 0:
        scheduler.remove_all_jobs()
        scheduler.shutdown()

        await tear_up_db(ouranos_db)
