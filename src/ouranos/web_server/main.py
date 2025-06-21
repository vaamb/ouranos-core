#!/usr/bin/python3
from __future__ import annotations

import asyncio
import socket
from typing import Callable

from uvicorn import Config, Server

from ouranos.core.config import ConfigDict, ConfigHelper
from ouranos.core.database.init import print_registration_token
from ouranos.sdk import Functionality, Plugin
from ouranos.web_server.system_monitor import SystemMonitor


class _AppWrapper:
    def __init__(self, start: Callable[[], None], stop: Callable[[], None]):
        self.start = start
        self.stop = stop


class ServerWithOuranosConfig(Server):
    """An uvicorn server that sets the Ouranos config when starting to serve"""
    def __init__(
            self,
            config: Config,
            ouranos_config: ConfigDict,
    ) -> None:
        super().__init__(config)
        self.ouranos_config = ouranos_config

    async def serve(self, sockets: list[socket.socket] | None = None) -> None:
        if not ConfigHelper.config_is_set():
            ConfigHelper.set_config_and_configure_logging(self.ouranos_config)
        with self.capture_signals():
            await self._serve(sockets)


class WebServer(Functionality):
    def __init__(
            self,
            config: ConfigDict,
            **kwargs
    ) -> None:
        """The web-facing API and socketio events.
        This functionality exposes Ouranos main API functions to the web. It
        relies on `FastAPI` for the HTTP server and `python-socketio` to manage
        socketio events.

        :param config_profile: The configuration profile to provide. Either a
        `BaseConfig` or its subclass, a str corresponding to a profile name
        accessible in a `config.py` file, or None to take the default profile.
        :param config_override: A dictionary containing some overriding
        parameters for the configuration.
        :param kwargs: Other parameters to pass to the base class.
        """
        super().__init__(config, **kwargs)
        self.system_monitor = SystemMonitor()

        workers = self.config["WEB_SERVER_WORKERS"] or self.config["API_WORKERS"] or 0
        global_workers_limit: int | None = self.config["GLOBAL_WORKERS_LIMIT"]
        if global_workers_limit is not None:
            workers = min(workers, global_workers_limit)

        # Configure uvicorn server
        server_cfg = Config(
            "ouranos.web_server.factory:create_app", factory=True, loop="auto",
            host=self.config["API_HOST"], port=self.config["API_PORT"],
            workers=workers,
            reload=self.config["WEB_SERVER_RELOAD"], reload_delay=0.5,
            log_config=None, server_header=False, date_header=False,
        )
        self.server = ServerWithOuranosConfig(server_cfg, ouranos_config=self.config)
        self.app: _AppWrapper

        # Reloading server
        if self.server.config.should_reload:
            from uvicorn.supervisors import ChangeReload

            sock = self.server.config.bind_socket()
            reload = ChangeReload(
                self.server.config, target=self.server.run, sockets=[sock])

            self.app = _AppWrapper(reload.run, reload.should_exit.set)

        # Multiprocess server
        elif workers > 0:
            # Works on linux, not on Windows
            from uvicorn.supervisors import Multiprocess

            sock = self.server.config.bind_socket()
            multi = Multiprocess(
                self.server.config, target=self.server.run, sockets=[sock])

            self.app = _AppWrapper(multi.run, multi.should_exit.set)

        # Single process server
        else:
            def start():
                asyncio.ensure_future(self.server.serve())

            def stop():
                self.server.should_exit = True

            self.app = _AppWrapper(start, stop)

    async def initialize(self) -> None:
        await print_registration_token(self.logger)

    async def startup(self):
        self.app.start()
        await self.system_monitor.start()

    async def shutdown(self):
        await self.system_monitor.stop()
        self.app.stop()
        await asyncio.sleep(1)  # Allow ChangeReload and Multiprocess to exit


web_server_plugin = Plugin(
    functionality=WebServer,
    description="""Launch Ouranos' Web server

    The Web server is the main communication point between Ouranos and the user.
    It provides a web api that allows the user to get data from the database. It
    can also send data to the Aggregator that will dispatch them to the
    requested Gaia's instance
    """,
)

# The web server directly manages its workers via uvicorn
web_server_plugin.compute_number_of_workers = lambda: 0
