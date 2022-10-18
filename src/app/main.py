#!/usr/bin/python3
from __future__ import annotations

import asyncio
import logging

import click
import uvicorn
from uvicorn.loops.auto import auto_loop_setup

import default
from config import default_profile, get_specified_config
from src.core.g import db, set_config_globally


@click.command()
@click.option(
    "--config-profile",
    type=str,
    default=default_profile,
    help="Configuration profile to use as defined in config.py.",
    show_default=True,
)
def main(
        config_profile: str,
) -> None:
    asyncio.run(
        run(
            config_profile,
        )
    )


async def run(
        config_profile: str | None = None,
) -> None:
    # Get and set config globally
    config = get_specified_config(config_profile)
    app_name = config["APP_NAME"].lower()
    from setproctitle import setproctitle
    setproctitle(f"{app_name}-app")
    set_config_globally(config)
    from src.core.g import config
    # Configure logger and tokenizer
    from src.core.utils import configure_logging, Tokenizer
    configure_logging(config)
    logger: logging.Logger = logging.getLogger(app_name)
    Tokenizer.secret_key = config["SECRET_KEY"]
    # Init database
    logger.info("Initializing the database")
    from src.core.database import models  # noqa
    db.init(config)
    from src.core.database.init import create_base_data
    await create_base_data(logger)
    # Start the app
    loop: asyncio.AbstractEventLoop = asyncio.get_event_loop()
    logger.debug("Creating the App")
    app = App(config)
    logger.info("Starting the App")
    app.start()
    # Run as long as requested
    from src.core.runner import Runner
    runner = Runner()
    await asyncio.sleep(0.1)
    runner.add_signal_handler(loop)
    await runner.wait_forever()
    app.stop()
    await runner.exit()


class App:
    def __init__(
            self,
            config: dict | None = None,
    ) -> None:
        from src.core.g import config as global_config
        self.config = config or global_config
        if not self.config:
            raise RuntimeError(
                "Either provide a config dict or set config globally with "
                "g.set_app_config"
            )
        use_subprocess: bool = (
                self.config.get("SERVER_RELOAD", False) or
                (self.config.get("START_API", default.START_API) and
                 self.config.get("API_WORKERS", default.API_WORKERS) > 1)
        )
        auto_loop_setup(use_subprocess)
        host: str = self.config["API_HOST"]
        port: int = self.config["API_PORT"]
        self.server_cfg = uvicorn.Config(
            "src.app.factory:create_app", factory=True,
            host=host, port=port,
            workers=self.config.get("API_WORKERS", default.API_WORKERS),
            loop="auto",
            server_header=False, date_header=False,
        )
        self.server = uvicorn.Server(self.server_cfg)
        if self.server_cfg.should_reload:
            # TODO: make it work, handle stop and shutdown
            from uvicorn.supervisors import ChangeReload

            sock = self.server_cfg.bind_socket()
            reload = ChangeReload(
                self.server_cfg, target=self.server.run, sockets=[sock]
            )
            self._app = reload
            self._app.start = reload.run
        elif self.server_cfg.workers > 1:
            # Works on linux, not on Windows
            from uvicorn.supervisors import Multiprocess

            sock = self.server_cfg.bind_socket()
            multi = Multiprocess(
                self.server_cfg, target=self.server.run, sockets=[sock]
            )
            self._app = multi
            self._app.start = multi.startup
            self._app.stop = multi.shutdown
        else:
            class Holder:
                __slots__ = ("start", "stop")

            def start():
                asyncio.ensure_future(self.server.serve())

            def stop():
                self.server.should_exit = True
            self._app = Holder()
            self._app.start = start
            self._app.stop = stop

    def start(self):
        self._app.start()

    def stop(self):
        self._app.stop()


if __name__ == "__main__":
    main()
