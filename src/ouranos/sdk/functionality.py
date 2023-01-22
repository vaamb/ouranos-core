from __future__ import annotations

import asyncio
from logging import Logger, getLogger
import re
import typing as t

from ouranos import current_app, configure_logging, db, scheduler, setup_config
from ouranos.core.database.init import create_base_data


if t.TYPE_CHECKING:
    from ouranos.core.config import config_type, profile_type


pattern = re.compile(r'(?<!^)(?=[A-Z])')


class _SetUp:
    done: bool = False


class Functionality:
    def __init__(
            self,
            config_profile: "profile_type" = None,
            config_override: dict | None = None,
            *args,
            root: bool = False,
            **kwargs
    ) -> None:
        self.name = pattern.sub('_', self.__class__.__name__).lower()
        if not _SetUp.done:
            # Change process name
            from setproctitle import setproctitle
            if root:
                setproctitle(f"ouranos")
            else:
                setproctitle(f"ouranos-{self.name}")
            # Setup config
            config = setup_config(config_profile)
            # Configure logging
            configure_logging(config)
            logger: Logger = getLogger("ouranos")
            # Init database
            logger.info("Initializing the database")
            db.init(current_app.config)
            asyncio.ensure_future(create_base_data(logger))
            _SetUp.done = True

        self.config: config_type = current_app.config
        if config_override:
            self.config.update(config_override)
        if root:
            self.logger: Logger = getLogger(f"ouranos")
        else:
            self.logger: Logger = getLogger(f"ouranos.{self.name}")
        self._status = False

    def _start(self):
        raise NotImplementedError

    def _stop(self):
        raise NotImplementedError

    def start(self):
        if not self._status:
            # Start the scheduler
            self.logger.debug("Starting the Scheduler")
            scheduler.start()
            # Start the functionality
            self._start()
            self._status = True
        else:
            raise RuntimeError(
                f"{self.__class__.__name__} has already started"
            )

    def stop(self):
        if self._status:
            # Stop the scheduler
            self.logger.debug("Stopping the Scheduler")
            # Stop the functionality
            scheduler.remove_all_jobs()
            scheduler.shutdown()
            self._stop()
            self._status = False
        else:
            raise RuntimeError(
                f"{self.__class__.__name__} is not running"
            )


def run_functionality_forever(
        functionality_cls: t.Type[Functionality],
        config_profile: str | None = None,
        *args,
        **kwargs
):
    async def run(
            functionality_cls: t.Type[Functionality],
            config_profile: str | None = None,
            *args,
            **kwargs
    ):
        # Start the functionality
        loop: asyncio.AbstractEventLoop = asyncio.get_event_loop()
        functionality = functionality_cls(config_profile, *args, **kwargs)
        functionality.start()
        # Run until it receives the stop signal
        from ouranos.sdk.runner import Runner
        runner = Runner()
        await runner.run_until_stop(loop)
        functionality.stop()
        await runner.exit()

    asyncio.run(
        run(functionality_cls, config_profile, *args, **kwargs)
    )
