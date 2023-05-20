from __future__ import annotations

import asyncio
from logging import Logger, getLogger
import re
import typing as t
from typing import Type

from ouranos import configure_logging, current_app, db, scheduler, setup_config
from ouranos.core.database.init import (
    create_base_data, print_registration_token)


if t.TYPE_CHECKING:
    from ouranos.core.config import ConfigDict, profile_type


pattern = re.compile(r'(?<!^)(?=[A-Z])')


class _SetUp:
    done: bool = False


class Functionality:
    def __init__(
            self,
            config_profile: "profile_type" = None,
            config_override: dict | None = None,
            *,
            auto_setup_config: bool = True,
            root: bool = False,
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
        :param auto_setup_config: Whether to automatically set up the
        configuration or not. Should remain `True` for most cases, except during
        testing or when config is set up manually prior to the use of the
        `Functionality`
        :param root: Whether the functionality is managing other (sub)-
        functionalities or not. Should remain `False` for most cases.
        """
        self.name = pattern.sub('_', self.__class__.__name__).lower()
        if not _SetUp.done and auto_setup_config:
            # Change process name
            from setproctitle import setproctitle
            if root:
                setproctitle(f"ouranos")
            else:
                setproctitle(f"ouranos-{self.name}")
            # Setup config
            try:
                config = setup_config(config_profile)
                configure_logging(config)
            except RuntimeError:
                config = current_app.config
            logger: Logger = getLogger("ouranos")
            if not root and "memory://" in config["DISPATCHER_URL"]:
                logger.warning(
                    "Using Ouranos as microservices and the memory-based "
                    "dispatcher, this will lead to errors as some data won't "
                    "be transferred between the different microservices"
                )
            _SetUp.done = True

        self.config: ConfigDict = current_app.config
        if config_override:
            self.config = self.config.copy()
            self.config.update(config_override)
        if root:
            self.logger: Logger = getLogger(f"ouranos")
        else:
            self.logger: Logger = getLogger(f"ouranos.{self.name}")
        self._status = False

    @staticmethod
    async def init_the_db(generate_registration_token: bool = True):
        logger: Logger = getLogger("ouranos")
        logger.info("Initializing the database")
        db.init(current_app.config)
        await create_base_data(logger)
        if generate_registration_token:
            await print_registration_token(logger)

    def _start(self):
        raise NotImplementedError

    def _stop(self):
        raise NotImplementedError

    def start(self):
        if not self._status:
            # Start the functionality
            self._start()
            self._status = True
        else:
            raise RuntimeError(
                f"{self.__class__.__name__} has already started"
            )

    def stop(self):
        if self._status:
            # Stop the functionality
            self._stop()
            self._status = False
        else:
            raise RuntimeError(
                f"{self.__class__.__name__} is not running"
            )


def run_functionality_forever(
        functionality_cls: Type[Functionality],
        config_profile: str | None = None,
        *args,
        **kwargs
):
    async def inner_func(
            _functionality_cls: Type[Functionality],
            _config_profile: str | None = None,
            *_args,
            **_kwargs
    ):
        # Start the functionality
        loop: asyncio.AbstractEventLoop = asyncio.get_event_loop()
        functionality = functionality_cls(config_profile, *args, **kwargs)
        await functionality_cls.init_the_db()
        functionality.logger.info("Starting the scheduler")
        scheduler.start()
        functionality.start()
        # Run until it receives the stop signal
        from ouranos.sdk.runner import Runner
        runner = Runner()
        await runner.run_until_stop(loop)
        functionality.stop()
        functionality.logger.info("Stopping the scheduler")
        scheduler.remove_all_jobs()
        scheduler.shutdown()
        await runner.exit()

    asyncio.run(
        inner_func(functionality_cls, config_profile, *args, **kwargs)
    )
