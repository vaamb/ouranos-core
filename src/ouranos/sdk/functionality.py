from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from logging import Logger, getLogger
import os
import re
import typing as t
from typing import Type
import warnings

from ouranos import current_app, db, scheduler, setup_loop
from ouranos.core.config import ConfigHelper
from ouranos.core.database.init import (
    create_base_data, print_registration_token)
from ouranos.sdk.runner import Runner


if t.TYPE_CHECKING:
    from ouranos.core.config import ConfigDict, profile_type


pattern = re.compile(r'(?<!^)(?=[A-Z])')


class _State:
    db_initialized: bool = False


class Functionality(ABC):
    _db_initialized: bool = False
    _is_microservice: bool = True
    _runner = Runner()
    workers: int = 0

    def __init__(
            self,
            config_profile: "profile_type" = None,
            config_override: dict | None = None,
            *,
            auto_setup_config: bool = True,
            root: bool = False,
            microservice: bool | None = None,
            **kwargs
    ) -> None:
        """ Create a new `Functionality` instance.
        `Functionality` instances are the base working units of Ouranos. They
        can be divided into core functionalities (the aggregator and the web
        api) and all the plugins.

        :param config_profile: The configuration profile to provide. Either a
        `BaseConfig` or its subclass, a str corresponding to a profile name
        accessible in a `config.py` file, or None to take the default profile.
        :param config_override: A dictionary containing some overriding
        parameters for the configuration.
        :param auto_setup_config: bool, Whether to automatically set up the
        configuration or not. Should remain `True` for most cases, except during
        testing or when config is set up manually prior to the use of the
        `Functionality`
        :param root: bool, Whether the functionality is managing other (sub)-
        functionalities or not. Should remain `False` for most cases.
        """
        self.name = format_functionality_name(self.__class__)
        self.logger: Logger = getLogger(f"ouranos.{self.name}")

        self.config_profile = config_profile
        if not ConfigHelper.config_is_set():
            ConfigHelper.set_config_and_configure_logging(config_profile)
        self.config: ConfigDict = current_app.config
        if config_override:
            self.config = self.config.copy()
            self.config.update(config_override)

        if microservice is not None:
            self._is_microservice = microservice
        if self._is_microservice and "memory://" in self.config["DISPATCHER_URL"]:
            self.logger.warning(
                "Using Ouranos as microservices and the memory-based dispatcher. "
                "This could lead to errors as some data won't "
                "be transferred between the different microservices.")

        self._status = False

    async def init_the_db(self, generate_registration_token: bool = True) -> None:
        self.logger.info("Initializing the database")
        db.init(current_app.config)
        await create_base_data(self.logger)
        if generate_registration_token:
            await print_registration_token(self.logger)
        _State.db_initialized = True

    async def initialize(self) -> None:
        if not _State.db_initialized:
            await self.init_the_db()
        scheduler.start()

    async def post_initialize(self) -> None:
        pass

    async def post_shutdown(self) -> None:
        pass

    async def clear(self) -> None:
        scheduler.remove_all_jobs()
        scheduler.shutdown()

    async def startup(self) -> None:
        if self._status:
            raise RuntimeError(
                f"{self.__class__.__name__} has already started"
            )
        # Start the functionality
        pid = os.getpid()
        self.logger.info(
            f"Starting Ouranos' {self.__class__.__name__} [{pid}]")
        try:
            await self._startup()
        except Exception as e:
            self.logger.error(
                f"Error while starting. Error msg: "
                f"`{e.__class__.__name__}: {e}`")
        else:
            self.logger.info(
                f"Ouranos' {self.__class__.__name__} has been started [{pid}]")
            self._status = True

    async def shutdown(self) -> None:
        if not self._status:
            raise RuntimeError(
                f"Ouranos' {self.__class__.__name__} is not running"
            )
        # Stop the functionality
        pid = os.getpid()
        self.logger.info(
            f"Stopping Ouranos' {self.__class__.__name__} [{pid}]")
        try:
            await self._shutdown()
        except asyncio.CancelledError as e:
            self.logger.error(
                f"Error while shutting down. Error msg: "
                f"`{e.__class__.__name__}: {e}`")
        else:
            self._status = False
            self.logger.info(
                f"Ouranos' {self.__class__.__name__} has been stopped [{pid}]")

    @abstractmethod
    async def _startup(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def _shutdown(self) -> None:
        raise NotImplementedError

    async def pre_run(self) -> None:
        await self.initialize()
        await self.post_initialize()
        await self.startup()
        pid = os.getpid()
        self.logger.info(
            f"{self.__class__.__name__} running [{pid}] (Press CTRL+C to quit)")

    async def post_run(self) -> None:
        await self.shutdown()
        await self.post_shutdown()
        await self.clear()

    def run(self) -> None:
        setup_loop()
        asyncio.run(self._run())

    async def _run(self) -> None:
        await self.pre_run()
        await self._runner.run_until_stop()
        await self.post_run()

    def stop(self):
        self._runner.stop()


def format_functionality_name(functionality: Type[Functionality]) -> str:
    return pattern.sub('_', functionality.__name__).lower()


def run_functionality_forever(
        functionality_cls: Type[Functionality],
        config_profile: str | None = None,
        *args,
        **kwargs
):
    warnings.warn(
        "`run_functionality_forever` is deprecated, run the functionality "
        "via a `Plugin` instead",
        DeprecationWarning
    )
    functionality = functionality_cls(config_profile, *args, **kwargs)
    functionality.run()
