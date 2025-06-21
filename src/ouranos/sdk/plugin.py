from __future__ import annotations

import asyncio
from collections import namedtuple
from logging import getLogger, Logger
import multiprocessing
from multiprocessing.context import SpawnContext, SpawnProcess
import typing as t
from typing import ClassVar, Type, TypeVar

import click
from click import Command

from ouranos import current_app, setup_loop
from ouranos.core.config import ConfigDict, ConfigHelper
from ouranos.core.utils import parse_str_value
from ouranos.sdk import Functionality
from ouranos.sdk.functionality import format_functionality_name
from ouranos.sdk.runner import Runner, runner

if t.TYPE_CHECKING:
    from ouranos.core.config import profile_type


F = TypeVar("F", bound=Functionality)

multiprocessing.allow_connection_pickling()
spawn: SpawnContext = multiprocessing.get_context("spawn")

Route = namedtuple("Route", ("path", "endpoint"))


class Plugin:
    _runner: ClassVar[Runner] = runner

    def __init__(
            self,
            functionality: Type[F],
            name: str | None = None,
            command: Command | None = None,
            routes: list[Route] | None = None,
            description: str | None = None,
    ) -> None:
        """Create a new plugin.

        Plugins manage functionality instances, optionally running them in
        separate processes. They handle initialization, startup, and shutdown.

        :param functionality: The functionality class to manage.
        :param name: Plugin name (defaults to functionality name).
        :param command: Click command for CLI interface.
        :param routes: FastAPI routes to register.
        :param description: Plugin description for CLI help.
        """
        self.name: str = name or format_functionality_name(functionality)
        self.logger: Logger = getLogger(f"ouranos.{self.name}-plugin")
        self._functionality: Type[F] = functionality
        self._instance: F | None = None
        self._subprocesses: list[SpawnProcess] = []
        self._status: bool = False
        self._command: Command | None = command
        self._routes: list[Route] = routes or []
        self._description: str | None = description
        self.config: ConfigDict | None = None
        self._kwargs: dict = {}

    def __repr__(self) -> str:
        return f"<Plugin({self.name}, status={self._status})>"

    def __lt__(self, other) -> bool:
        if not isinstance(other, Plugin):
            return NotImplemented
        return self.name < other.name

    def _fmt_exc(self, e: BaseException) -> str:
        return f"`{e.__class__.__name__}: {e}`"

    @property
    def is_started(self) -> bool:
        """Check if the plugin is currently running."""
        return self._status

    @property
    def functionality(self) -> Type[F]:
        """Get the managed functionality class."""
        return self._functionality

    @property
    def instance(self) -> F:
        """Get the functionality instance (raises if not started)."""
        if self._instance is None:
            raise RuntimeError(f"Plugin {self.name} is not started")
        return self._instance

    @property
    def subprocesses(self) -> list[SpawnProcess]:
        """Get the list of subprocesses (if any)."""
        return self._subprocesses

    @property
    def kwargs(self) -> dict:
        """Get the initialization kwargs."""
        return self._kwargs

    @kwargs.setter
    def kwargs(self, value: dict):
        """Update the initialization kwargs."""
        self._kwargs.update(value)

    def setup_config(
            self,
            config_profile: profile_type,
            config_override: dict | None = None,
    ) -> None:
        """Initialize configuration for the plugin.

        :param config_profile: Configuration profile to use.
        :param config_override: Optional configuration overrides.
        """
        if not ConfigHelper.config_is_set():
            ConfigHelper.set_config_and_configure_logging(
                config_profile, config_override)
        self.config = current_app.config
        self._kwargs["config"] = self.config

    def compute_number_of_workers(self) -> int:
        """Calculate the number of worker processes needed.

        :return: Number of worker processes to spawn.
        """
        if self.config is None:
            raise RuntimeError("Config not set. Call setup_config() first")

        workers = self._functionality.workers
        func_workers = self.config.get(f"{self.name.upper()}_WORKERS")
        if func_workers is not None:
            workers = parse_str_value(func_workers)

        global_limit = self.config.get("GLOBAL_WORKERS_LIMIT")
        if global_limit is not None:
            workers = min(workers, parse_str_value(global_limit))

        return max(0, workers)

    def _run_in_subprocess(self) -> None:
        """Run functionality in a subprocess."""
        try:
            if not ConfigHelper.config_is_set():
                ConfigHelper.set_config_and_configure_logging(self.config)
            self._instance.run()
        except Exception as e:
            self.logger.error(f"Subprocess failed: {e}")
            raise

    def has_subprocesses(self) -> bool:
        """Check if any subprocesses are running."""
        return bool(self._subprocesses)

    async def startup(self) -> None:
        """Start the functionality, optionally in subprocesses.

        :raises RuntimeError: If already started or config not set.
        """
        if self._status:
            raise RuntimeError(f"{self.name} already started")
        if self.config is None:
            raise RuntimeError("Config not set. Call setup_config() first")

        workers = self.compute_number_of_workers()
        self._instance = self._functionality(**self._kwargs)

        try:
            if workers > 0:
                for worker in range(workers):
                    process_name = f"{self.functionality.__name__}-{worker}"
                    process = spawn.Process(
                        target=self._run_in_subprocess,
                        daemon=True,
                        name=process_name,
                    )
                    process.start()
                    self._subprocesses.append(process)
            else:
                await self._instance.startup()
        except Exception as e:
            self.logger.error(f"Failed to start: {self._fmt_exc(e)}")
            raise
        else:
            self._status = True
            self.logger.info(f"Started {self.name} with {workers} workers")

    async def shutdown(self) -> None:
        """Stop the functionality and cleanup resources.

        :raises RuntimeError: If not running.
        """
        if not self._status:
            raise RuntimeError(f"{self.name} is not running")

        try:
            if self.has_subprocesses():
                # Cleanup subprocesses
                for process in self._subprocesses:
                    if process.is_alive():
                        process.terminate()
                        process.join(timeout=5.0)
                        if process.is_alive():
                            self.logger.warning(
                                f"Process {process.name} did not terminate cleanly")
                            process.kill()
                            process.join()
                self._subprocesses.clear()
            else:
                # Cleanup main instance
                await self._instance.shutdown()
        except Exception as e:
            self.logger.error(f"Error during shutdown: {self._fmt_exc(e)}")
            raise
        finally:
            self._status = False
            self.logger.info(f"Stopped {self.name}")

    def run_as_standalone(self) -> None:
        """Run the functionality as a standalone process."""
        from setproctitle import setproctitle
        setproctitle(f"ouranos-{self.name}")

        setup_loop()
        self._kwargs["microservice"] = True
        asyncio.run(self._run_as_standalone())

    async def _run_as_standalone(self) -> None:
        """Internal async method for standalone execution."""
        try:
            await self.startup()
            await self._runner.run_until_stop()
        finally:
            await self.shutdown()

    # Command handling
    def has_command(self) -> bool:
        """Check if the plugin has a CLI command."""
        return self._command is not None

    @property
    def command(self) -> Command:
        """Get or create the CLI command for the plugin."""
        if self._command is None:
            @click.command(self.name, help=self._description)
            @click.option(
                "--config-profile", "-c",
                type=str,
                default=None,
                help="Configuration profile to use as defined in config.py.",
                show_default=True,
            )
            @click.option(
                "--config-override", "-co",
                type=str,
                multiple=True,
                help="Configuration overrides in key=value format",
                show_default=True,
            )
            def command(
                    config_profile: str | None,
                    config_override: list[str],
            ) -> None:
                """Run the plugin as a standalone service."""
                config_override_str = config_override
                config_override = {}
                for overridden in config_override_str:
                    key, value = overridden.split("=")
                    config_override[key] = parse_str_value(value)

                self.setup_config(config_profile, config_override)
                self.run_as_standalone()

            self._command = command
        return self._command

    # Routes
    def has_route(self) -> bool:
        return len(self._routes) > 0

    def add_route(self, route: Route) -> None:
        self._routes.append(route)

    @property
    def routes(self) -> list[Route]:
        return self._routes
