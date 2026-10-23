from __future__ import annotations

import asyncio
from logging import getLogger, Logger
import os
import typing as t
from typing import ClassVar

import uvloop

from ouranos.core.config import ConfigDict
from ouranos.core.utils import format_error
from ouranos.sdk.resources import acquire_common_resources, release_common_resources
from ouranos.sdk.runner import Runner, runner

if t.TYPE_CHECKING:
    from ouranos.sdk.plugin import Plugin


class StartupError(Exception): ...


class Host:
    _runner: ClassVar[Runner] = runner

    def __init__(
            self,
            name: str,
            config: ConfigDict,
            plugins: list[Plugin],
    ) -> None:
        """Create a new host.

        A host is the root of an Ouranos process: it prepares the resources
        shared by its plugins, starts them (all or none) and stops them once
        a stop signal is received.

        :param name: Host name, also used as the process title.
        :param config: The configuration to provide as a `BaseConfigDict`.
        :param plugins: The plugins to run, in their startup order. Their
                        config and kwargs must already be set.
        """
        self.name: str = name
        self.config: ConfigDict = config
        self.plugins: list[Plugin] = plugins
        logger_name = name
        if logger_name.startswith("ouranos-"):
            logger_name = logger_name.replace("-", ".", 1)
        logger_name = logger_name.replace("-", "_")
        self.logger: Logger = getLogger(f"{logger_name}.host")
        self._started: bool = False
        self._error_logged: bool = False

    def __repr__(self) -> str:
        return f"<Host({self.name}, status={self.started})>"

    @property
    def started(self) -> bool:
        """Return whether the host has started."""
        return self._started

    async def startup(self) -> None:
        """Prepare the common resources, then start every plugin or none of them.

        If a plugin fails to start, the ones already started are stopped, the
        common resources are released and the error is re-raised.
        """
        if self.started:
            raise RuntimeError(f"{self.name} has already started")

        pid = os.getpid()
        self.logger.info(f"Starting {self.name} [{pid}]")

        # Prepare the shared resources before any plugin, so that subprocess
        #  workers don't race on the database initialization
        await acquire_common_resources(self.config, self.logger)

        started: list[Plugin] = []
        try:
            for plugin in self.plugins:
                await plugin.startup()
                started.append(plugin)
        except Exception as e:
            self.logger.critical(
                f"Failed to start plugin '{plugin.name}', stopping the plugins "
                f"already started. {format_error(e)}", exc_info=e)
            for started_plugin in reversed(started):
                await self._try_stop_plugin(started_plugin)
            await release_common_resources()
            raise StartupError(f"Failed to start plugin '{plugin.name}'") from e

        self._started = True
        self.logger.info(f"{self.name} has been started [{pid}]")

    async def shutdown(self) -> None:
        """Stop every running plugin, in the reverse order they were started,
        then release the common resources.

        A plugin failing to stop is logged and doesn't prevent the following
        ones from being stopped.
        """
        if not self.started:
            raise RuntimeError(f"{self.name} is not running")

        pid = os.getpid()
        self.logger.info(f"Stopping {self.name} [{pid}]")

        try:
            for plugin in reversed(self.plugins):
                if plugin.is_started:
                    await self._try_stop_plugin(plugin)
        finally:
            await release_common_resources()
            self._started = False

        self.logger.info(f"{self.name} has been stopped [{pid}]")

    async def _try_stop_plugin(self, plugin: Plugin) -> None:
        try:
            await plugin.shutdown()
        except (Exception, asyncio.CancelledError) as e:
            # `CancelledError` deliberately swallowed, see
            #  `Functionality.complete_shutdown()`
            self.logger.error(
                f"Failed to stop plugin '{plugin.name}'. {format_error(e)}",
                exc_info=e)

    async def keep_alive(self) -> None:
        """Restart the dead workers of every plugin.

        A plugin failing to restart its workers is logged and doesn't prevent
        the following ones from being kept alive.
        """
        # Workers also receive the stop signal, don't restart them while stopping
        if self._runner.stopping:
            return
        for plugin in self.plugins:
            try:
                await plugin.keep_alive()
            except Exception as e:
                self.logger.error(
                    f"Failed to keep plugin '{plugin.name}' alive. {format_error(e)}",
                    exc_info=e)

    def run(self) -> None:
        """Run the host until a stop signal is received."""
        from setproctitle import setproctitle
        setproctitle(self.name)

        try:
            uvloop.run(self._run())
        except Exception:
            if not self._error_logged:
                # The error should not have happened and is not logged, raise it anyway
                raise
            if self.config["DEVELOPMENT"] or self.config["DEBUG"] or self.config["TESTING"]:
                raise
            raise SystemExit(1)

    async def _run(self) -> None:
        self._runner.add_signal_handler()
        # Don't show the traceback on error if not in debugging mode
        if not self.config["DEBUG"]:
            import sys

            def exception_handler(exception_type, exception, _traceback):
                print(f"{exception_type.__name__}: {exception}")

            sys.excepthook = exception_handler

        self._error_logged = False
        try:
            await self.startup()
        except Exception as e:
            if not isinstance(e, StartupError):
                self.logger.critical(
                    f"Error while starting {self.name}. {format_error(e)}", exc_info=e)
            self._error_logged = True
            raise
        else:
            await self._runner.run_until_stop([self.keep_alive])
        finally:
            if self.started:
                try:
                    await self.shutdown()
                except Exception as e:
                    self.logger.critical(
                        f"Error while shutting down {self.name}. {format_error(e)}",
                        exc_info=e)
                    self._error_logged = True
                    raise

    def stop(self) -> None:
        """Stop the host gracefully."""
        self._runner.stop()
