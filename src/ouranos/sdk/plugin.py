from __future__ import annotations

import asyncio
from collections import namedtuple
import multiprocessing
from multiprocessing.context import SpawnContext, SpawnProcess
import typing as t
from typing import Type, TypeVar

from click import Command, Option

from ouranos import current_app, setup_loop
from ouranos.core.config import ConfigHelper
from ouranos.sdk import Functionality, run_functionality_forever
from ouranos.sdk.functionality import format_functionality_name

if t.TYPE_CHECKING:
    from ouranos.core.config import profile_type


F = TypeVar("F", bound=Functionality)

multiprocessing.allow_connection_pickling()
spawn: SpawnContext = multiprocessing.get_context("spawn")

Route = namedtuple("Route", ("path", "endpoint"))


class Plugin:
    def __init__(
            self,
            functionality: Type[F],
            name: str | None = None,
            command: Command | None = None,
            routes: list[Route] | None = None,
            config_profile: profile_type = None,
            **kwargs,
    ) -> None:
        """Create a new plugin.

        Plugins are used to register functionality to the functionality manager.
        They are also used to register routes to the web api.
        A plugin will take care of initializing the linked functionality,
        starting it, and stopping it, in a different process if needed.

        :param functionality: The functionality to register.
        :param name: The name of the plugin.
        :param command: The click command to register.
        :param routes: The routes to register.
        :param kwargs: The kwargs to pass to the functionality.
        """
        self._functionality: Type[F] = functionality
        self._instance: F | None = None
        self._subprocesses: list[SpawnProcess] = []
        self._status: bool = False
        self.name: str = name or format_functionality_name(functionality)
        self._command: Command | None = command
        self._routes: list[Route] = routes or []
        self._kwargs = kwargs
        self._kwargs["config_profile"] = config_profile
        self._kwargs["auto_setup_config"] = self._functionality.workers > 0

    @property
    def is_started(self) -> bool:
        return self._status

    @property
    def functionality_cls(self) -> Type[F]:
        return self._functionality

    @property
    def instance(self) -> F:
        return self._instance

    @property
    def kwargs(self) -> dict:
        return self._kwargs

    @kwargs.setter
    def kwargs(self, value: dict):
        self._kwargs.update(value)

    def compute_number_of_workers(self) -> int:
        # The config is required in order to compute the actual number of
        #  workers needed (we need to compare the functionality and the config)
        if not ConfigHelper.config_is_set():
            config_profile = self._kwargs["config_profile"]
            ConfigHelper.set_config_and_configure_logging(config_profile)

        workers = self._functionality.workers
        func_workers = current_app.config.get(f"{self.name.upper()}_WORKERS")
        if func_workers is not None:
            workers = func_workers
        global_workers_limit: int | None = current_app.config["GLOBAL_WORKERS_LIMIT"]
        if global_workers_limit is not None:
            workers = min(workers, global_workers_limit)
        return workers

    def _run_in_subprocess(self) -> None:
        self._instance = self._functionality(**self._kwargs)
        self._instance.run()

    def has_subprocesses(self) -> bool:
        return len(self._subprocesses) > 0

    async def start(self) -> None:
        """Initialize and start the functionality. If needed the functionality
        will be started in one or more subprocesses."""
        if self._status:
            raise RuntimeError(f"{self.name} has already started")
        workers = self.compute_number_of_workers()
        try:
            if workers:
                assert not self._instance
                for _ in range(workers):
                    process = spawn.Process(
                        target=self._run_in_subprocess,
                        daemon=True,
                    )
                    process.start()
                    self._subprocesses.append(process)
            else:
                assert not self._subprocesses
                self._instance = self._functionality(**self._kwargs)
                await self._instance.pre_run()
        except Exception as e:
            self._functionality.logger.error(
                f"Error while starting. Error msg: "
                f"`{e.__class__.__name__}: {e}`")
        else:
            self._status = True

    async def stop(self) -> None:
        """Stop the functionality and the subprocesses if needed."""
        if not self._status:
            raise RuntimeError(f"{self.name} is not running")
        try:
            if self.has_subprocesses:
                for process in self._subprocesses:
                    process.terminate()
                    process.join()
            else:
                await self._instance.post_run()
        except Exception as e:
            self._functionality.logger.error(
                f"Error while shutting down. Error msg: "
                f"`{e.__class__.__name__}: {e}`")
        else:
            self._status = False

    def run_as_standalone(self) -> None:
        setup_loop()
        self._kwargs["is_root"] = True
        asyncio.run(self._run_as_standalone())

    async def _run_as_standalone(self) -> None:
        await self.start()
        await self._functionality._runner.run_until_stop()
        await self.stop()

    # Command
    def has_command(self) -> bool:
        return self._command is not None

    @property
    def command(self) -> Command:
        if self._command is None:
            func = asyncio.run(
                run_functionality_forever(self.functionality_cls)
            )
            command = Command("main", callback=func)
            option = Option(
                "--config-profile",
                type=str,
                default=None,
                help="Configuration profile to use as defined in config.py.",
                show_default=True
            )
            command.params.append(option)
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
