#!/usr/bin/python3
from __future__ import annotations

import asyncio
import logging
import typing as t

import click
import uvicorn
from uvicorn.loops.auto import auto_loop_setup

from ouranos import db, setup_config
from ouranos.sdk import Functionality


if t.TYPE_CHECKING:
    from ouranos.core.config import profile_type


@click.command()
@click.option(
    "--config-profile",
    type=str,
    default=None,
    help="Configuration profile to use as defined in config.py.",
    show_default=True,
)
def main(
        config_profile: str | None,
) -> None:
    asyncio.run(
        run(
            config_profile,
        )
    )


async def run(
        config_profile: str | None = None,
) -> None:
    from setproctitle import setproctitle
    setproctitle("ouranos-web_server")
    # Setup config
    config = setup_config(config_profile)
    logger: logging.Logger = logging.getLogger("ouranos.web_server")
    # Init database
    logger.info("Initializing the database")
    db.init(config)
    from ouranos.core.database.init import create_base_data
    await create_base_data(logger)
    # Start the app
    loop: asyncio.AbstractEventLoop = asyncio.get_event_loop()
    logger.debug("Creating the Web server")
    web_server = WebServer(config)
    logger.info("Starting the Web server")
    web_server.start()
    # Run as long as requested
    from ouranos.sdk.runner import Runner
    runner = Runner()
    await asyncio.sleep(0.1)
    runner.add_signal_handler(loop)
    await runner.wait_forever()
    web_server.stop()
    await runner.exit()


class WebServer(Functionality):
    def __init__(
            self,
            config_profile: "profile_type" = None,
            config_override: dict | None = None,
    ) -> None:
        super().__init__(config_profile, config_override)

        use_subprocess: bool = (
                self.config["SERVER_RELOAD"] or
                (self.config["START_API"] and
                 self.config["API_WORKERS"] > 1)
        )
        auto_loop_setup(use_subprocess)
        host: str = self.config["API_HOST"]
        port: int = self.config["API_PORT"]
        self.server_cfg = uvicorn.Config(
            "ouranos.web_server.factory:create_app", factory=True,
            host=host, port=port,
            workers=self.config["API_WORKERS"],
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

    def _start(self):
        self._app.start()

    def _stop(self):
        self._app.stop()
