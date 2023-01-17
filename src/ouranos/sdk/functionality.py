from __future__ import annotations

import logging
import re
import typing as t

from ouranos import current_app, configure_logging, db, setup_config
from ouranos.core.database.init import create_base_data


if t.TYPE_CHECKING:
    from ouranos.core.config import config_profile


pattern = re.compile(r'(?<!^)(?=[A-Z])')


class _SetUp:
    done: bool = False


class Functionality:
    def __init__(
            self,
            config_profile: "config_profile" = None,
            config_override: dict | None = None, 
    ) -> None:
        name = pattern.sub('_', self.__class__.__name__).lower()
        if not _SetUp.done:
            # Change process name
            from setproctitle import setproctitle
            setproctitle(f"ouranos.{name}")
            # Setup config
            config = setup_config(config_profile)
            # Configure logging
            configure_logging(config)
            logger: logging.Logger = logging.getLogger("ouranos")
            # Init database
            logger.info("Initializing the database")
            db.init(current_app.config)
            await create_base_data(logger)
            _SetUp.done = True

        self.logger: logging.Logger = logging.getLogger(f"ouranos.{name}")
        self.config = current_app.config
        if config_override:
            self.config.update(config_override)
