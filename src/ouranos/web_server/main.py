#!/usr/bin/python3
from __future__ import annotations

import asyncio
import typing as t

import click
import uvicorn
from uvicorn.loops.auto import auto_loop_setup

from ouranos.sdk import Functionality, run_functionality_forever


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
    """Launch Ouranos'Web server

    The Web server is the main communication point between Ouranos and the user.
    It provides a web api that allows the user to get data from the database. It
    can also send data to the Aggregator that will dispatch them to the
    requested Gaia's instance
    """
    run_functionality_forever(WebServer, config_profile)


class WebServer(Functionality):
    def __init__(
            self,
            config_profile: "profile_type" = None,
            config_override: dict | None = None,
    ) -> None:
        super().__init__(config_profile, config_override)
        self.logger.info("Creating Ouranos web server")
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
        self.logger.info("Starting the web server")
        self._app.start()

    def _stop(self):
        self._app.stop()
