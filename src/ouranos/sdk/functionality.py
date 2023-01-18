from __future__ import annotations

import asyncio
from logging import Logger, getLogger
import re
import typing as t

from ouranos import current_app, configure_logging, db, setup_config
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
            *,
            root: bool = False,
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
            self._start()
            self._status = True
        else:
            raise RuntimeError(
                f"{self.__class__.__name__} has already started"
            )

    def stop(self):
        if self._status:
            self._stop()
            self._status = False
        else:
            raise RuntimeError(
                f"{self.__class__.__name__} is not running"
            )
