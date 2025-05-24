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
    common_initialized: bool = False


class Functionality(ABC):
    _is_microservice: bool = True
    _runner = Runner()
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

        if not ConfigHelper.config_is_set():
            ConfigHelper.set_config_and_configure_logging(config)
        self.config: ConfigDict = current_app.config

        if microservice is not None:
            self._is_microservice = microservice
        if self._is_microservice and "memory://" in self.config["DISPATCHER_URL"]:
            self.logger.warning(
                "Using Ouranos as microservices and the memory-based dispatcher. "
                "This could lead to errors as some data won't "
                "be transferred between the different microservices.")

        self._status = False

    def _fmt_exc(self, e: BaseException) -> str:
        return f"`{e.__class__.__name__}: {e}`"

    async def init_the_db(self, generate_registration_token: bool = True) -> None:
        self.logger.info("Initializing the database")
        db.init(current_app.config)
        await create_base_data(self.logger)
        if generate_registration_token:
            await print_registration_token(self.logger)

    # Functions automatically called during the lifecycle
    async def _init_common(self) -> None:
        await self.init_the_db()
        scheduler.start()
        _State.common_initialized = True

    async def _clear_common(self) -> None:
        scheduler.remove_all_jobs()
        scheduler.shutdown()

    # Functions automatically called during the lifecycle that can be tweaked
    async def initialize(self) -> None:
        pass

    @abstractmethod
    async def _startup(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def _shutdown(self) -> None:
        raise NotImplementedError

    async def post_shutdown(self) -> None:
        pass

    # Lifecycle functions
    async def startup(self) -> None:
        if self._status:
            raise RuntimeError(
                f"{self.__class__.__name__} has already started"
            )
        pid = os.getpid()
        self.logger.info(
            f"Starting Ouranos' {self.__class__.__name__} [{pid}]")
        try:
            if not _State.common_initialized:
                await self._init_common()
            await self.initialize()
            await self._startup()
        except Exception as e:
            self.logger.error(
                f"Error while starting [{pid}]. Error msg: {self._fmt_exc(e)}")
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
            await self.post_shutdown()
        except asyncio.CancelledError as e:
            self.logger.error(
                f"Error while shutting down. Error msg: {self._fmt_exc(e)}")
        else:
            self._status = False
            self.logger.info(
                f"Ouranos' {self.__class__.__name__} has been stopped [{pid}]")

    def run(self) -> None:
        setup_loop()
        asyncio.run(self._run())

    async def _run(self) -> None:
        await self.startup()
        await self._runner.run_until_stop()
        await self.shutdown()

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
