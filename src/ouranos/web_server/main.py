#!/usr/bin/python3
from __future__ import annotations

import asyncio
import typing as t
from typing import Callable

import uvicorn
from uvicorn.loops.auto import auto_loop_setup

from ouranos.sdk import Functionality, Plugin
from ouranos.web_server.system_monitor import SystemMonitor


if t.TYPE_CHECKING:
    from ouranos.core.config import profile_type


class _AppWrapper:
    def __init__(self, start: Callable[[], None], stop: Callable[[], None]):
        self.start = start
        self.stop = stop


class WebServer(Functionality):
    def __init__(
            self,
            config_profile: "profile_type" = None,
            config_override: dict | None = None,
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
        super().__init__(config_profile, config_override, **kwargs)
        self.system_monitor = SystemMonitor()
        use_subprocess: bool = (
            self.config["API_SERVER_RELOAD"] or
            self.config["API_WORKERS"] > 1
        )
        auto_loop_setup(use_subprocess)
        host: str = self.config["API_HOST"]
        port: int = self.config["API_PORT"]
        self.server_cfg = uvicorn.Config(
            "ouranos.web_server.factory:create_app", factory=True,
            host=host, port=port,
            workers=self.config["API_WORKERS"],
            loop="auto",
            log_config=None, server_header=False, date_header=False,
        )
        self.server = uvicorn.Server(self.server_cfg)
        self._app: _AppWrapper
        if self.server_cfg.should_reload:
            # TODO: make it work, handle stop and shutdown
            from uvicorn.supervisors import ChangeReload

            sock = self.server_cfg.bind_socket()
            reload = ChangeReload(
                self.server_cfg, target=self.server.run, sockets=[sock]
            )
            self._app = _AppWrapper(reload.run, reload.shutdown)
        elif self.server_cfg.workers > 1:
            # Works on linux, not on Windows
            from uvicorn.supervisors import Multiprocess

            sock = self.server_cfg.bind_socket()
            multi = Multiprocess(
                self.server_cfg, target=self.server.run, sockets=[sock]
            )
            self._app = _AppWrapper(multi.startup, multi.shutdown)
        else:
            def start():
                asyncio.ensure_future(self.server.serve())

            def stop():
                self.server.should_exit = True

            self._app = _AppWrapper(start, stop)

    async def _startup(self):
        self._app.start()
        await self.system_monitor.start()

    async def _shutdown(self):
        await self.system_monitor.stop()
        self._app.stop()


web_server_plugin = Plugin(
    functionality=WebServer,
    description="""Launch Ouranos' Web server

    The Web server is the main communication point between Ouranos and the user.
    It provides a web api that allows the user to get data from the database. It
    can also send data to the Aggregator that will dispatch them to the
    requested Gaia's instance
    """,
)
