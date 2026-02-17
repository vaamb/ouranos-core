from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from logging import Logger, getLogger
import os
import re
from typing import ClassVar, Type

from ouranos import db, scheduler, setup_loop
from ouranos.core.config import ConfigDict
from ouranos.core.database.init import (
    check_db_revision, create_db_tables, insert_default_data)
from ouranos.sdk.runner import Runner, runner


_PATTERN = re.compile(r'(?<!^)(?=[A-Z])')


class _CommonResourcesState:
    def __init__(self):
        self.initialized: bool = False
        self.used_by: int = 0

    def register(self) -> None:
        self.used_by += 1

    def unregister(self) -> None:
        if self.used_by <= 0:
            raise RuntimeError("There are no more registered resources")
        self.used_by -= 1


class Functionality(ABC):
    _common_resources_state: ClassVar[_CommonResourcesState] = _CommonResourcesState()
    _runner: ClassVar[Runner] = runner

    _is_microservice: bool = True
    workers: int = 0

    def __init__(
            self,
            config: ConfigDict,
            *,
            microservice: bool | None = None,
            **kwargs
    ) -> None:
        """ Create a new `Functionality` instance.
        `Functionality` instances are the base working units of Ouranos. They
        can be divided into core functionalities (the aggregator and the web
        api) and all the plugins.

        :param config: The configuration to provide as a `BaseConfigDict`.
        :param microservice: Whether the functionality is run as a microservice.
                             If set to false, some config checks will be done.
        """
        self.name = format_functionality_name(self.__class__)
        self.logger: Logger = getLogger(f"ouranos.{self.name}")
        self.config: ConfigDict = config
        self._status: bool = False
        self._error_logged: bool = False

        if microservice is not None:
            self._is_microservice = microservice
        if self._is_microservice and "memory://" in self.config["DISPATCHER_URL"]:
            self.logger.warning(
                "Using Ouranos as microservices and the memory-based dispatcher. "
                "This could lead to errors as some data won't "
                "be transferred between the different microservices.")

    @property
    def started(self) -> bool:
        """Return whether the functionality has started."""
        return self._status

    def _fmt_exc(self, e: BaseException) -> str:
        """Format exception for logging."""
        return f"Error msg: `{e.__class__.__name__}: {e}`"

    async def init_the_db(self) -> None:
        """Initialize the database."""
        self.logger.info("Initializing the database")
        db.init(self.config)
        await create_db_tables()
        if not self.config["TESTING"]:  # Revisions aren't used in tests (yet ?)
            await check_db_revision()
        await insert_default_data()
        self.logger.debug("Database initialized")

    async def init_the_scheduler(self) -> None:
        self.logger.info("Initializing the scheduler")
        scheduler.start()
        self.logger.debug("Scheduler initialized")

    async def _init_common(self) -> None:
        """Initialize common resources."""
        if not Functionality._common_resources_state.initialized:
            await self.init_the_db()
            await self.init_the_scheduler()
            Functionality._common_resources_state.initialized = True

        Functionality._common_resources_state.register()

    async def _clear_common(self) -> None:
        """Clear common resources."""
        # Decref the common resources
        Functionality._common_resources_state.unregister()
        # If no functionality is using the common resources, clear them
        if Functionality._common_resources_state.used_by == 0:
            scheduler.remove_all_jobs()
            scheduler.shutdown()

            for engine in db.engines.values():
                await engine.dispose()

    async def initialize(self) -> None:
        """Hook for subclasses to initialize resources."""
        pass

    @abstractmethod
    async def startup(self) -> None:
        """Start the functionality (implemented by subclasses)."""

    @abstractmethod
    async def shutdown(self) -> None:
        """Shutdown the functionality (implemented by subclasses)."""

    async def post_shutdown(self) -> None:
        """Hook for subclasses to perform post-shutdown cleanup."""
        pass

    async def complete_startup(self) -> None:
        """Start the functionality and all required resources."""
        if self.started:
            raise RuntimeError(f"{self.__class__.__name__} has already started")

        pid = os.getpid()
        self.logger.info(f"Starting Ouranos' {self.__class__.__name__} [{pid}]")

        try:
            await self._init_common()
        except Exception:
            await self._clear_common()
            raise
        await self.initialize()
        await self.startup()

        self._status = True
        self.logger.info(f"Ouranos' {self.__class__.__name__} started successfully [{pid}]")

    async def complete_shutdown(self) -> None:
        """Shutdown the functionality and clean up resources."""
        if not self.started:
            raise RuntimeError(f"Ouranos' {self.__class__.__name__} is not running")

        pid = os.getpid()
        self.logger.info(f"Stopping Ouranos' {self.__class__.__name__} [{pid}]")

        try:
            await self.shutdown()
            await self.post_shutdown()
        except asyncio.CancelledError as e:
            self.logger.error(f"Error while shutting down [{pid}]. {self._fmt_exc(e)}")

        await self._clear_common()

        self._status = False
        self.logger.info(f"Ouranos' {self.__class__.__name__} stopped [{pid}]")

    def run(self, reraise: bool = False) -> None:
        """Run the functionality until completion or interruption."""
        setup_loop()
        try:
            asyncio.run(self._run())
        except Exception:
            if not self._error_logged:
                # The error should not have happened and is not logged, raise it anyway
                raise
            if (
                    reraise
                    or self.config["DEVELOPMENT"] or self.config["DEBUG"] or self.config["TESTING"]
            ):
                raise

    async def _run(self) -> None:
        pid = os.getpid()
        self._error_logged = False
        try:
            await self.complete_startup()
        except Exception as e:
            self.logger.error(f"Error while starting [{pid}]. {self._fmt_exc(e)}")
            self.logger.info(f"Will stop [{pid}]")
            self._error_logged = True
            raise
        else:
            # `run_until_stop()` cannot raise
            await self._runner.run_until_stop()
        finally:
            if self.started:
                try:
                    await self.complete_shutdown()
                except Exception as e:
                    self.logger.error(f"Error while shutting down [{pid}]. {self._fmt_exc(e)}")
                    self._error_logged = True
                    raise

    def stop(self) -> None:
        """Stop the functionality gracefully."""
        if not self.started:
            return

        self._runner.stop()


def format_functionality_name(functionality: Type[Functionality]) -> str:
    """Convert CamelCase class name to snake_case functionality name."""
    return _PATTERN.sub('_', functionality.__name__).lower()
