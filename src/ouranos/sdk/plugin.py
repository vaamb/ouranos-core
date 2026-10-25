from __future__ import annotations

from abc import ABC, abstractmethod
import asyncio
from collections import namedtuple
from dataclasses import dataclass
from logging import getLogger, Logger
import multiprocessing
from multiprocessing.context import SpawnContext, SpawnProcess
import time
import typing as t
from typing import Any, Awaitable, TypeVar

import click
from click import Command, Group

from ouranos import current_app
from ouranos.core.config import ConfigDict, ConfigHelper, consts
from ouranos.core.exceptions import ContractVersionError
from ouranos.core.utils import parse_config_override
from ouranos.sdk import Functionality
from ouranos.sdk.functionality import format_functionality_name
from ouranos.sdk.host import Host

if t.TYPE_CHECKING:
    from ouranos.core.config import profile_type


F = TypeVar("F", bound=Functionality)
C = TypeVar("C", bound=Command | Group)

multiprocessing.allow_connection_pickling()
spawn: SpawnContext = multiprocessing.get_context("spawn")

Route = namedtuple("Route", ("path", "endpoint"))

# Back off between the restarts of a worker that keeps dying: the first restart
#  is immediate, the next ones wait twice as long each time, up to the max delay
_RESTART_BASE_DELAY = 1.0
_RESTART_MAX_DELAY = 300.0
# A worker alive for that long is considered healthy and its back off is reset
_RESTART_RESET_AFTER = 600.0


class PluginExecutor(ABC):
    def __init__(
            self,
            functionality: type[F],
            workers: int,
            config: ConfigDict,
            logger: Logger,
            **kwargs,
    ) -> None:
        self.functionality: type[F] = functionality
        self.config: ConfigDict = config
        self.workers: int = workers
        self.logger: Logger = logger
        self.kwargs: dict[str, Any] = kwargs

    @abstractmethod
    async def start(self) -> None: ...

    @abstractmethod
    async def stop(self) -> None: ...

    @classmethod
    def initialize(
            cls,
            functionality: type[F],
            workers: int,
            config: ConfigDict,
            logger: Logger,
            **kwargs,
    ) -> PluginExecutor:
        if workers == 0:
            return _InProcessExecutor(functionality, 0, config, logger, **kwargs)
        else:
            return _SubprocessExecutor(functionality, workers, config, logger, **kwargs)

    async def keep_alive(self) -> None:
        pass


class _InProcessExecutor(PluginExecutor):
    def __init__(
            self, functionality: type[F], workers: int, config: ConfigDict,
            logger: Logger, **kwargs) -> None:
        super().__init__(functionality, workers, config, logger, **kwargs)
        self._instance: F | None = None

    @property
    def instance(self) -> Functionality:
        """Get the functionality instance (raises if not started)."""
        if self._instance is None:
            raise RuntimeError("Executor is not started")
        return self._instance

    async def start(self) -> None:
        # ty issue with TypeVar
        self._instance = self.functionality(config=self.config, **self.kwargs)  # ty: ignore[invalid-assignment]
        self.logger.debug("Starting in process executor...")
        try:
            await self.instance.complete_startup()
        except Exception:
            # `complete_startup()` already cleared the functionality resources
            self._instance = None
            raise
        else:
            self.logger.debug("In process executor started")

    async def stop(self) -> None:
        self.logger.debug("Stopping in process executor...")
        try:
            await self.instance.complete_shutdown()
        finally:
            self._instance = None
        self.logger.debug("In process executor stopped")


@dataclass
class _RestartState:
    started_at: float
    restarts: int = 0
    restart_at: float | None = None


class _SubprocessExecutor(PluginExecutor):
    def __init__(
            self, functionality: type[F], workers: int, config: ConfigDict,
            logger: Logger, **kwargs) -> None:
        super().__init__(functionality, workers, config, logger, **kwargs)
        self._subprocesses: list[SpawnProcess] | None = None
        self._restart_states: list[_RestartState] = []

    @property
    def subprocesses(self) -> list[SpawnProcess]:
        """Get the subprocesses list (raises if not started)."""
        if self._subprocesses is None:
            raise RuntimeError("Executor is not started")
        return self._subprocesses

    @staticmethod
    def _run_in_subprocess(
            functionality_cls: type[Functionality],
            config: ConfigDict,
            kwargs: dict,
    ) -> None:
        """Run a functionality in a subprocess.

        Static method so that spawned processes only pickle the functionality
        class and its kwargs, not the whole `Executor` (self), which holds
        unpicklable attributes such as the other subprocesses.
        """
        if not ConfigHelper.config_is_set():
            ConfigHelper.set_config_and_configure_logging(config)
        functionality_cls(config=config, **kwargs).run(reraise=True)

    async def _stop_processes(self, timeout: float) -> None:
        stop_tasks: list[Awaitable[None]] = []
        kill_tasks: list[Awaitable[None]] = []
        for process in self.subprocesses:
            if process.is_alive():
                self.logger.debug(f"Stopping process {process.name}")
                process.terminate()
                stop_task = asyncio.to_thread(process.join, timeout)
                stop_tasks.append(stop_task)
        await asyncio.gather(*stop_tasks)
        for process in self.subprocesses:
            if process.is_alive():
                self.logger.warning(
                    f"Process {process.name} did not terminate cleanly, killing it")
                process.kill()
                kill_task = asyncio.to_thread(process.join)
                kill_tasks.append(kill_task)
        await asyncio.gather(*kill_tasks)

    async def start(self) -> None:
        self._subprocesses = []
        self._restart_states = []
        self.logger.debug("Starting subprocess executor...")
        now = time.monotonic()
        try:
            for worker in range(self.workers):
                process_name = f"{self.functionality.__name__}-{worker}"
                process = self._spawn(process_name)
                self.subprocesses.append(process)
                self._restart_states.append(_RestartState(started_at=now))
                self.logger.debug(f"Started worker {process_name}")
        except Exception:
            # Clean up any already-started subprocesses on failure
            self.logger.warning("Failed to start subprocess executor, cleaning up")
            await self._stop_processes(1.0)
            self._subprocesses = None
            raise
        else:
            self.logger.debug("Subprocess executor started")

    async def stop(self) -> None:
        # Cleanup subprocesses
        self.logger.debug("Stopping subprocess executor...")
        await self._stop_processes(5.0)
        self._subprocesses = None
        self._restart_states.clear()
        self.logger.debug("Subprocess executor stopped")

    def _spawn(self, process_name: str) -> SpawnProcess:
        process = spawn.Process(
            target=self._run_in_subprocess,
            args=(self.functionality, self.config, self.kwargs),
            daemon=True,
            name=process_name,
        )
        process.start()
        return process

    async def keep_alive(self) -> None:
        now = time.monotonic()
        for idx, process in enumerate(self.subprocesses):
            state = self._restart_states[idx]
            if process.is_alive():
                if state.restarts and now - state.started_at > _RESTART_RESET_AFTER:
                    state.restarts = 0
                continue

            if state.restart_at is None:
                # Newly found dead: schedule its restart
                delay = 0.0
                if state.restarts:
                    delay = min(
                        _RESTART_BASE_DELAY * 2 ** (state.restarts - 1),
                        _RESTART_MAX_DELAY,
                    )
                state.restart_at = now + delay
                self.logger.warning(
                    f"Subprocess worker {process.name} has died (exit code "
                    f"{process.exitcode}), restarting it in {delay:.0f} s")
            if now < state.restart_at:
                continue

            # Reap the dead process before replacing it
            process.join()
            process_name = process.name
            process.close()

            self.subprocesses[idx] = self._spawn(process_name)
            state.started_at = now
            state.restarts += 1
            state.restart_at = None


class Extension:
    def __init__(
            self,
            name: str,
            *,
            contract_versions: dict[str, int],
            routes: list[Route] | None = None,
            description: str | None = None,
    ) -> None:
        """Create an API extension.

        Extensions add new routes to the API.

        :param name: Extension name.
        :param contract_versions: A dict with the contracts version needed.
        :param routes: FastAPI routes to register.
        :param description: Extension description.
        """
        self.name: str = name
        self.logger: Logger = getLogger(f"ouranos.{self.name}-extension")
        # Check contract versions
        self._check_contract_versions(contract_versions)
        self._routes: list[Route] = routes or []
        self._description: str | None = description

    def __repr__(self) -> str:
        return f"<Extension({self.name})>"

    def __lt__(self, other) -> bool:
        if not isinstance(other, Extension):
            return NotImplemented
        return self.name < other.name

    @property
    def routes(self) -> list[Route]:
        return self._routes

    def _check_contract_versions(self, contracts: dict[str, int]) -> None:
        """Check that the contract versions required by the plugin are compatible
        with Ouranos-core"""
        error_msgs: list[str] = []
        ouranos_contracts = {
            "gaia": consts.GAIA_CONTRACT,
            "rest": consts.REST_CONTRACT,
            "socketio": consts.SOCKETIO_CONTRACT,
        }
        for contract_name, value in contracts.items():
            ouranos_version = ouranos_contracts.get(contract_name.lower(), None)
            if ouranos_version is None:
                error_msgs.append(f"Contract '{contract_name}' not defined in Ouranos.")
            else:
                assert isinstance(ouranos_version, int)
                if ouranos_version > value:
                    error_msgs.append(
                        f"Plugin requires contract v.{value}, Ouranos provides "
                        f"v.{ouranos_version}. You might need to update the plugin."
                    )
                elif ouranos_version < value:
                    error_msgs.append(
                        f"Plugin requires contract v.{value}, Ouranos provides "
                        f"v.{ouranos_version}. You might need to update Ouranos-core."
                    )
        if error_msgs:
            raise ContractVersionError(" ".join(error_msgs))

    def has_route(self) -> bool:
        return len(self._routes) > 0

    def add_route(self, route: Route) -> None:
        self._routes.append(route)


class Plugin(Extension):
    def __init__(
            self,
            functionality: type[F],
            name: str | None = None,
            *,
            contract_versions: dict[str, int],
            command: Command | None = None,
            routes: list[Route] | None = None,
            description: str | None = None,
    ) -> None:
        """Create a new plugin.

        Plugins manage functionality instances, optionally running them in
        separate processes. They handle initialization, startup, and shutdown.

        :param functionality: The functionality class to manage.
        :param name: Plugin name (defaults to functionality name).
        :param contract_versions: A dict with the contracts version needed.
        :param command: Click command for CLI interface.
        :param routes: FastAPI routes to register.
        :param description: Plugin description for CLI help.
        """
        name: str = name or format_functionality_name(functionality).replace("_", "-")
        super().__init__(
            name, contract_versions=contract_versions, routes=routes,
            description=description)
        self.logger: Logger = getLogger(f"ouranos.{self.name}-plugin")
        self._functionality: type[F] = functionality
        self._executor: PluginExecutor | None = None
        self._command: Command | None = command
        self._config: ConfigDict | None = None
        self._kwargs: dict = {}

    def __repr__(self) -> str:
        return f"<Plugin({self.name}, status={self.is_started})>"

    def _fmt_exc(self, e: BaseException) -> str:
        return f"Error msg: `{e.__class__.__name__}: {e}`"

    @property
    def is_started(self) -> bool:
        """Check if the plugin is currently running."""
        return self._executor is not None

    @property
    def functionality(self) -> type[F]:
        """Get the managed functionality class."""
        # ty issue with TypeVar
        return self._functionality  #ty: ignore[invalid-return-type]

    @property
    def executor(self) -> PluginExecutor:
        if self._executor is None:
            raise RuntimeError(f"Plugin {self.name} is not started")
        return self._executor

    @property
    def kwargs(self) -> dict:
        """Get the initialization kwargs."""
        return self._kwargs

    @kwargs.setter
    def kwargs(self, value: dict):
        """Set the initialization kwargs."""
        self._kwargs = value

    def update_kwargs(self, value: dict) -> None:
        """Merge additional kwargs into the existing initialization kwargs."""
        self._kwargs.update(value)

    @property
    def config(self) -> ConfigDict:
        if self._config is None:
            raise ValueError("Config not set. Call setup_config() first")
        return self._config

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
        self._config = current_app.config

    def compute_number_of_workers(self) -> int:
        """Calculate the number of worker processes needed.

        :return: Number of worker processes to spawn.
        """
        if self.config is None:
            raise RuntimeError("Config not set. Call setup_config() first")

        workers = self.functionality.workers
        func_workers: str | None = self.config.get(f"{self.name.upper().replace('-', '_')}_WORKERS")
        if func_workers is not None:
            workers = int(func_workers)

        global_limit = self.config.get("GLOBAL_WORKERS_LIMIT")
        if global_limit is not None:
            workers = min(workers, int(global_limit))

        return max(0, workers)

    async def check_requirements(self) -> None:
        """Check if the requirements to start the plugin are met"""
        pass

    async def startup(self) -> None:
        """Start the functionality, optionally in subprocesses.

        :raises RuntimeError: If already started or config not set.
        """
        if self.is_started:
            raise RuntimeError(f"{self.name} already started")
        if self._config is None:
            raise RuntimeError("Config not set. Call setup_config() first")

        await self.check_requirements()

        workers = self.compute_number_of_workers()
        self.logger.info(f"Starting {self.name} with {workers} workers")
        executor = PluginExecutor.initialize(
            self.functionality, workers, self.config, self.logger, **self.kwargs)
        await executor.start()

        # Only expose the executor once it has started
        self._executor = executor
        self.logger.info(f"Started {self.name} with {workers} workers")

    async def shutdown(self) -> None:
        """Stop the functionality and cleanup resources.

        :raises RuntimeError: If not running.
        """
        if not self.is_started:
            raise RuntimeError(f"{self.name} is not running")

        self.logger.info(f"Stopping {self.name}")

        try:
            await self.executor.stop()
        finally:
            # Mark as stopped even on failure: the resources have been cleared
            self._executor = None

        self.logger.info(f"Stopped {self.name}")

    async def keep_alive(self) -> None:
        """Restart the dead workers of the plugin, if it is running."""
        if self.is_started:
            await self.executor.keep_alive()

    def run_as_standalone(self) -> None:
        """Run the functionality as a standalone process."""
        self._kwargs["microservice"] = True
        host = Host(f"ouranos-{self.name}", self.config, [self])
        host.run()

    # Command handling
    def has_command(self) -> bool:
        """Check if the plugin has a CLI command."""
        return self._command is not None

    def create_run_command(self, cmd_cls: type[C] | None = None) -> C:
        @click.command(self.name, cls=cmd_cls, help=self._description)
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
            try:
                config_override_dict = parse_config_override(config_override)
            except ValueError as e:
                raise click.BadParameter(
                    str(e),
                    param_hint="'--config-override'",
                )

            self.setup_config(config_profile, config_override_dict)
            self.run_as_standalone()

        return command  # ty: ignore[invalid-return-type]

    @property
    def command(self) -> Command:
        """Get or create the CLI command for the plugin."""
        if self._command is None:
            self._command = self.create_run_command()
        return self._command
