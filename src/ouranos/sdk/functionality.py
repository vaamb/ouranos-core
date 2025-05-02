from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from logging import Logger, getLogger
import os
from pathlib import Path
import re
import typing as t
from typing import Type

from ouranos import current_app, db, scheduler, setup_loop
from ouranos.core.config import ConfigHelper
from ouranos.core.database.init import (
    create_base_data, print_registration_token)
from ouranos.sdk.runner import Runner


if t.TYPE_CHECKING:
    from ouranos.core.config import ConfigDict, profile_type


pattern = re.compile(r'(?<!^)(?=[A-Z])')


class _SetUp:
    proc_name = False


class BaseFunctionality(ABC):
    _runner = Runner()
    workers: int = 0

    def __init__(
            self,
            config_profile: "profile_type" = None,
            config_override: dict | None = None,
            *,
            auto_setup_config: bool = True,
            microservice: bool = True,
            root: bool = False,
            **kwargs
    ) -> None:
        self.name = format_functionality_name(self.__class__)
        self.is_root = root
        if not self.is_proc_name_setup():
            # Change process name
            from setproctitle import setproctitle
            if "ouranos" in self.name:
                setproctitle(f"ouranos")
            else:
                setproctitle(f"ouranos-{self.name}")
            self.proc_name_has_been_setup()

        if auto_setup_config and not ConfigHelper.config_is_set():
            ConfigHelper.set_config_and_configure_logging(config_profile)

        self.config: ConfigDict = current_app.config
        if config_override:
            self.config = self.config.copy()
            self.config.update(config_override)

        if self.is_root:
            self.logger: Logger = getLogger(f"ouranos")
        else:
            self.logger: Logger = getLogger(f"ouranos.{self.name}")

        if not self.is_root:
            self.logger.info(f"Creating Ouranos' {self.name.capitalize()}")

        if microservice and "memory://" in self.config["DISPATCHER_URL"]:
            self.logger.warning(
                "Using Ouranos as microservices and the memory-based dispatcher "
                "or cache server, this could lead to errors as some data won't "
                "be transferred between the different microservices"
            )

        self._status = False

    def is_proc_name_setup(self) -> bool:
        return _SetUp.proc_name

    def proc_name_has_been_setup(self) -> None:
        _SetUp.proc_name = True

    async def init_the_db(self, generate_registration_token: bool = True) -> None:
        self.logger.info("Initializing the database")
        db.init(current_app.config)
        await create_base_data(self.logger)
        if generate_registration_token:
            await print_registration_token(self.logger)

    async def clean_the_db(self) -> None:
        self.logger.info("Cleaning the database cache")
        cache_uri = self.config["SQLALCHEMY_BINDS"]["transient"]
        cache_path = Path(cache_uri.split("///")[1])
        cache_path.unlink(missing_ok=True)

    async def initialize(self) -> None:
        await self.init_the_db()
        scheduler.start()

    async def post_initialize(self) -> None:
        pass

    async def post_shutdown(self) -> None:
        pass

    async def clear(self) -> None:
        scheduler.remove_all_jobs()
        scheduler.shutdown()
        await self.clean_the_db()

    async def startup(self):
        if not self._status:
            # Start the functionality
            pid = os.getpid()
            if self.is_root:
                self.logger.info(f"Starting Ouranos process [{pid}]")
            else:
                self.logger.info(
                    f"Starting Ouranos' {self.name.replace('_', ' ').capitalize()} "
                    f"process [{pid}]"
                )
            await self._startup()
            self._status = True
        else:
            raise RuntimeError(
                f"{self.__class__.__name__} has already started"
            )

    async def shutdown(self):
        if self._status:
            # Stop the functionality
            if self.is_root:
                self.logger.info(f"Stopping")
            else:
                self.logger.info(
                    f"Stopping Ouranos' {self.name.replace('_', ' ').capitalize()}")
            try:
                await self._shutdown()
            except asyncio.CancelledError as e:
                self.logger.error(
                    f"Error while shutting down. Error msg: "
                    f"`{e.__class__.__name__}: {e}`"
                )
            self._status = False
        else:
            raise RuntimeError(
                f"{self.__class__.__name__} is not running"
            )

    @abstractmethod
    async def _startup(self):
        raise NotImplementedError

    @abstractmethod
    async def _shutdown(self):
        raise NotImplementedError

    def run(self):
        setup_loop()
        asyncio.run(self._run())

    async def _run(self):
        await self.initialize()
        await self.post_initialize()
        await self.startup()
        self.logger.info(
            f"{self.name.replace('_', ' ').capitalize()} running (Press CTRL+C to quit)")
        await self._runner.run_until_stop()
        await self.shutdown()
        await self.post_shutdown()
        await self.clear()

    def stop(self):
        self._runner.stop()


class Functionality(BaseFunctionality, ABC):
    def __init__(
            self,
            config_profile: "profile_type" = None,
            config_override: dict | None = None,
            *,
            auto_setup_config: bool = True,
            **kwargs
    ):
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
        root = kwargs.pop("root", False)
        super().__init__(
            config_profile,
            config_override,
            auto_setup_config=auto_setup_config,
            root=root,
            **kwargs
        )


def format_functionality_name(functionality: Type[BaseFunctionality]) -> str:
    return pattern.sub('_', functionality.__name__).lower()


def run_functionality_forever(
        functionality_cls: Type[BaseFunctionality],
        config_profile: str | None = None,
        *args,
        **kwargs
):
    functionality = functionality_cls(config_profile, *args, **kwargs)
    functionality.run()
