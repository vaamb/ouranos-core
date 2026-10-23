#!/usr/bin/python3
from __future__ import annotations

import asyncio
from functools import partial
import logging
import sys
from typing import Awaitable, Callable

from fastapi import FastAPI
from uvicorn import Config, Server
from uvicorn.config import STARTUP_FAILURE

from ouranos.core.config import ConfigDict
from ouranos.core.database.init import print_registration_token
from ouranos.sdk import Functionality, Plugin
from ouranos.web_server.factory import create_app
from ouranos.web_server.system_monitor import SystemMonitor


def _create_app_or_exit(config: ConfigDict) -> FastAPI:
    # A wrapper function that set sys.exit(STARTUP_FAILURE) when `create_app`
    # raises an exception. This makes Uvicorn's `Multiprocess` stop trying to
    # respawn broken factories
    try:
        return create_app(config)
    except Exception:
        logger = logging.getLogger("ouranos.web_server")
        logger.exception("Failed to create the web server app")
        sys.exit(STARTUP_FAILURE)


class _AppWrapper:
    def __init__(self, start: Callable[[], Awaitable[None]], stop: Callable[[], Awaitable[None]]):
        self._start_fct = start
        self._stop_fct = stop
        self.started: bool = False

    async def start(self) -> None:
        await self._start_fct()
        self.started = True

    async def stop(self) -> None:
        await self._stop_fct()
        self.started = False


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

        :param config: The configuration to provide as a `(Base)ConfigDict`.
        :param kwargs: Other parameters to pass to the base class.
        """
        super().__init__(config, **kwargs)
        self.system_monitor = SystemMonitor()

        workers = self.config["WEB_SERVER_WORKERS"] or self.config["API_WORKERS"] or 0
        global_workers_limit: int | None = self.config["GLOBAL_WORKERS_LIMIT"]
        if global_workers_limit is not None:
            workers = min(workers, global_workers_limit)
        if workers > 1:
            # TODO: back cache invalidation with Redis (or similar) so session
            #  revocation is propagated across workers instead of being limited
            #  to the worker process that performed the write.
            self.logger.warning(
                f"Running with {workers} workers: session revocation (e.g. "
                f"password reset, session revoke) is only applied in the "
                f"worker that handled the request and won't be reflected in "
                f"other workers' user cache."
            )

        # Configure uvicorn server
        # `_create_app_or_exit()` uses `sys.exit()`, allowing `Multiprocess` stop
        # spawning broken factories
        app_factory = _create_app_or_exit if workers > 0 else create_app
        server_cfg = Config(
            partial(app_factory, self.config), factory=True, loop="auto",
            host=self.config["API_HOST"], port=self.config["API_PORT"],
            workers=workers, log_config=None, server_header=False, date_header=False,
        )
        self.server = Server(server_cfg)
        self.app: _AppWrapper

        # Same process server
        if workers == 0:
            async def start():
                asyncio.ensure_future(self.server.serve())
                while not self.server.started:
                    await asyncio.sleep(0.1)

            async def stop():
                self.server.should_exit = True
                await self.server._wait_tasks_to_complete()

            self.app = _AppWrapper(start, stop)

        # Multiprocess server
        else:
            # Works on linux, not on Windows
            from uvicorn.supervisors import Multiprocess

            sock = self.server.config.bind_socket()
            multi = Multiprocess(self.server.config, sockets=[sock])

            task: asyncio.Task | None = None

            async def start() -> None:
                nonlocal task
                task = asyncio.create_task(asyncio.to_thread(multi.run))
                try:
                    await wait_for_a_worker(task)
                except BaseException:
                    # Don't leave `multi.run()` running, the process would hang at exit
                    await stop()
                    raise

            async def wait_for_a_worker(task_: asyncio.Task) -> None:
                host, port = sock.getsockname()[:2]
                # Spawned workers import Ouranos before serving: wait for one to listen
                for _ in range(100):
                    if task_.done():
                        # `multi.run()` returned early (crash, or a worker STARTUP_FAILURE)
                        await task_
                        raise RuntimeError("Web server workers stopped during startup")
                    try:
                        _, writer = await asyncio.open_connection(host, port)
                    except OSError:
                        await asyncio.sleep(0.1)
                    else:
                        writer.close()
                        await writer.wait_closed()
                        return
                raise TimeoutError("No web server worker started within 10s")

            async def stop() -> None:
                nonlocal task
                assert task is not None
                multi.should_exit.set()
                try:
                    await asyncio.wait_for(asyncio.shield(task), timeout=5)
                except TimeoutError:
                    self.logger.warning("Web server workers did not stop within 5s")
                task = None
                sock.close()

            self.app = _AppWrapper(start, stop)

    async def initialize(self) -> None:
        await print_registration_token()

    async def startup(self):
        await self.app.start()
        await self.system_monitor.start()

    async def shutdown(self):
        await self.system_monitor.stop()
        await self.app.stop()


web_server_plugin = Plugin(
    WebServer,
    contract_versions={},  # Provides rest and socketio contracts
    description="""Launch Ouranos' Web server

    The Web server is the main communication point between Ouranos and the user.
    It provides a web api that allows the user to get data from the database. It
    can also send data to the Aggregator that will dispatch them to the
    requested Gaia's instance
    """,
)

# The web server directly manages its workers via uvicorn
web_server_plugin.compute_number_of_workers = lambda: 0  # ty: ignore[invalid-assignment]
