from __future__ import annotations

from abc import ABC
from dataclasses import dataclass, field
import multiprocessing
from multiprocessing.context import SpawnContext, SpawnProcess
import typing as t
from typing import Type

from ouranos.core.plugins_manager import PluginManager
from ouranos.sdk.functionality import (
    BaseFunctionality, format_functionality_name, Functionality)


if t.TYPE_CHECKING:
    from ouranos.core.config import profile_type


multiprocessing.allow_connection_pickling()
spawn: SpawnContext = multiprocessing.get_context("spawn")


@dataclass
class FunctionalityWrapper:
    functionality_cls: Type[Functionality]
    workers: int = 0
    kwargs: dict = field(default_factory=dict)
    instance: Functionality | None = None
    process: list[SpawnProcess] = field(default_factory=list)


class FunctionalityManager(BaseFunctionality, ABC):
    def __init__(
            self,
            config_profile: "profile_type" = None,
            config_override: dict | None = None,
            functionalities: list[Type[Functionality]] | None = None,
            *,
            auto_setup_config: bool = True,
            use_multiprocess: bool = False,
            **kwargs
    ):
        super().__init__(
            config_profile,
            config_override,
            auto_setup_config=auto_setup_config,
            root=True,
            **kwargs
        )
        self.config_override = config_override
        self.use_multiprocess = use_multiprocess
        self.plugin_manager = PluginManager()
        self.functionalities: dict[str, FunctionalityWrapper] = {}
        functionalities = functionalities or []
        for functionality in functionalities:
            self.wrap_functionality(functionality)

    def register_plugins(self, omit_excluded: bool = True) -> None:
        self.plugin_manager.register_plugins(omit_excluded)
        plugin_functionalities: list[Type[Functionality]] = [
            plugin.functionality_cls for plugin in
            self.plugin_manager.plugins.values()
        ]
        for functionality in plugin_functionalities:
            self.wrap_functionality(functionality)

    def wrap_functionality(self, functionality: Type[Functionality]) -> None:
        workers = functionality.workers
        func_name = format_functionality_name(functionality)
        func_workers_limit: int | None = self.config.get(
            f"{func_name.upper()}_WORKERS")
        if func_workers_limit is not None and workers > func_workers_limit:
            workers = func_workers_limit
        global_workers_limit: int | None = self.config["WORKERS"]
        if global_workers_limit is not None and workers > global_workers_limit:
            workers = global_workers_limit

        kwargs = {
            "config_override": self.config_override,
            "auto_setup_config": False,
            "microservice": False if workers == 0 else True,
        }

        self.functionalities[func_name] = FunctionalityWrapper(
            functionality, workers, kwargs)

    add_functionality = wrap_functionality

    @staticmethod
    def instantiate_functionality(functionality_wrapper: FunctionalityWrapper) -> None:
        if functionality_wrapper.workers > 0:
            functionality_name = format_functionality_name(
                functionality_wrapper.functionality_cls)
            raise ValueError(
                f"Functionality '{functionality_name}' should be run as a "
                f"worker"
            )
        functionality_cls = functionality_wrapper.functionality_cls
        kwargs = functionality_wrapper.kwargs
        functionality = functionality_cls(**kwargs)
        functionality_wrapper.instance = functionality

    @staticmethod
    async def init_async_func(functionality_wrapper: FunctionalityWrapper) -> None:
        if functionality_wrapper.workers > 0:
            functionality_name = format_functionality_name(
                functionality_wrapper.functionality_cls)
            raise ValueError(
                f"Functionality '{functionality_name}' should be run as a "
                f"worker"
            )
        await functionality_wrapper.instance.post_initialize()

    async def post_initialize(self):
        for functionality_wrapper in self.functionalities.values():
            if functionality_wrapper.workers > 0:
                # Will be done in subprocess
                pass
            else:
                self.instantiate_functionality(functionality_wrapper)
                await self.init_async_func(functionality_wrapper)

    async def post_shutdown(self) -> None:
        for functionality_wrapper in self.functionalities.values():
            if functionality_wrapper.workers > 0:
                # Will be done in subprocess
                pass
            else:
                await functionality_wrapper.instance.post_shutdown()

    @staticmethod
    def run_in_subprocess(functionality_wrapper: FunctionalityWrapper) -> None:
        functionality_cls = functionality_wrapper.functionality_cls
        kwargs = functionality_wrapper.kwargs
        functionality = functionality_cls(**kwargs)
        functionality.run()

    async def _startup(self) -> None:
        for functionality_wrapper in self.functionalities.values():
            if functionality_wrapper.workers > 0:
                for _ in range(functionality_wrapper.workers):
                    # Might be broken
                    process = spawn.Process(
                        target=self.run_in_subprocess,
                        kwargs={
                            "functionality_wrapper": functionality_wrapper,
                        }
                    )
                    process.start()
                    functionality_wrapper.process.append(process)
            else:
                await functionality_wrapper.instance.startup()

    async def _shutdown(self) -> None:
        functionalities = [*self.functionalities.keys()]
        functionalities.reverse()
        for functionality_name in functionalities:
            functionality_wrapper = self.functionalities[functionality_name]
            if functionality_wrapper.workers > 0:
                for process in functionality_wrapper.process:
                    process: SpawnProcess
                    process.terminate()
                    process.join()
            elif isinstance(functionality_wrapper.instance, Functionality):
                await functionality_wrapper.instance.shutdown()
            else:
                raise ValueError("Unrecognized type of functionality process")
