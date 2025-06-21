from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from logging import Logger, getLogger
import os
import re
from typing import ClassVar, Type
import warnings

from ouranos import db, scheduler, setup_loop
from ouranos.core.config import ConfigDict
from ouranos.core.database.init import create_base_data
from ouranos.sdk.runner import Runner, runner


pattern = re.compile(r'(?<!^)(?=[A-Z])')


class _State:
    common_initialized: bool = False


class Functionality(ABC):
    _is_microservice: bool = True
    _runner: ClassVar[Runner] = runner
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

        if microservice is not None:
            self._is_microservice = microservice
        if self._is_microservice and "memory://" in self.config["DISPATCHER_URL"]:
            self.logger.warning(
                "Using Ouranos as microservices and the memory-based dispatcher. "
                "This could lead to errors as some data won't "
                "be transferred between the different microservices.")

    def _fmt_exc(self, e: BaseException) -> str:
        """Format exception for logging."""
        return f"`{e.__class__.__name__}: {e}`"

    async def init_the_db(self) -> None:
        """Initialize the database."""
        try:
            self.logger.info("Initializing the database")
            db.init(self.config)
            await create_base_data(self.logger)
        except Exception as e:
            self.logger.error(f"Database initialization failed: {self._fmt_exc(e)}")
            raise

    async def _init_common(self) -> None:
        """Initialize common resources."""
        if _State.common_initialized:
            return

        try:
            await self.init_the_db()
            scheduler.start()
            _State.common_initialized = True
        except Exception as e:
            self.logger.error(f"Common initialization failed: {self._fmt_exc(e)}")
            raise

    async def _clear_common(self) -> None:
        """Clear common resources."""
        if not _State.common_initialized:
            return

        try:
            scheduler.remove_all_jobs()
            scheduler.shutdown()
        except Exception as e:
            self.logger.error(f"Failed to clear common resources: {self._fmt_exc(e)}")
            raise

    async def initialize(self) -> None:
        """Hook for subclasses to initialize resources."""
        pass

    @abstractmethod
    async def startup(self) -> None:
        """Start the functionality (implemented by subclasses)."""
        raise NotImplementedError

    @abstractmethod
    async def shutdown(self) -> None:
        """Shutdown the functionality (implemented by subclasses)."""
        raise NotImplementedError

    async def post_shutdown(self) -> None:
        """Hook for subclasses to perform post-shutdown cleanup."""
        pass

    async def complete_startup(self) -> None:
        """Start the functionality and all required resources."""
        if self._status:
            raise RuntimeError(f"{self.__class__.__name__} has already started")

        pid = os.getpid()
        self.logger.info(f"Starting Ouranos' {self.__class__.__name__} [{pid}]")
        
        try:
            await self._init_common()
            await self.initialize()
            await self.startup()
        except Exception as e:
            self.logger.error(f"Error while starting [{pid}]: {self._fmt_exc(e)}")
            raise
        else:
            self.logger.info(f"Ouranos' {self.__class__.__name__} started successfully [{pid}]")
            self._status = True

    async def complete_shutdown(self) -> None:
        """Shutdown the functionality and clean up resources."""
        if not self._status:
            raise RuntimeError(f"Ouranos' {self.__class__.__name__} is not running")
            
        pid = os.getpid()
        self.logger.info(f"Stopping Ouranos' {self.__class__.__name__} [{pid}]")

        try:
            await self.shutdown()
            await self.post_shutdown()
        except asyncio.CancelledError:
            self.logger.warning("Shutdown was cancelled")
        finally:
            self._status = False
            self.logger.info(f"Ouranos' {self.__class__.__name__} stopped [{pid}]")

    def run(self) -> None:
        """Run the functionality until completion or interruption."""
        try:
            setup_loop()
            asyncio.run(self._run())
        except Exception as e:
            self.logger.error(f"Fatal error in run loop: {self._fmt_exc(e)}")
            raise

    async def _run(self) -> None:
        await self.complete_startup()
        await self._runner.run_until_stop()
        await self.complete_shutdown()

    def stop(self) -> None:
        """Stop the functionality gracefully."""
        if not self._status:
            return

        self._runner.stop()


def format_functionality_name(functionality: Type[Functionality]) -> str:
    """Convert CamelCase class name to snake_case functionality name."""
    return pattern.sub('_', functionality.__name__).lower()


def run_functionality_forever(
        functionality_cls: Type[Functionality],
        config_profile: str | None = None,
        *args,
        **kwargs
) -> None:
    """
    Deprecated: Run a functionality forever.
    Use Plugin instead.
    """
    warnings.warn(
        "`run_functionality_forever` is deprecated, run the functionality "
        "via a `Plugin` instead",
        DeprecationWarning,
        stacklevel=2
    )
    functionality = functionality_cls(config_profile, *args, **kwargs)
    functionality.run()
