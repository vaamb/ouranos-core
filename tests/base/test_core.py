from contextlib import suppress
import logging
from multiprocessing import Manager
from pathlib import Path
import signal
from time import monotonic, sleep
from types import SimpleNamespace
import click
from click.testing import CliRunner
import pytest
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ouranos import current_app
from ouranos.core.config import consts, ConfigDict, ConfigHelper
from ouranos.core.exceptions import ContractVersionError
from ouranos.core.plugins_manager import PluginManager
from ouranos.core.utils import SingletonMeta
from ouranos.sdk.plugin import (
    _InProcessExecutor, _SubprocessExecutor, Extension, Functionality, Plugin, Route,
    spawn)
from ouranos.sdk.tests.plugin import DummyFunctionality


def _ignore_sigterm(ready) -> None:
    # Module-level so that spawned processes can pickle it
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    ready.set()
    sleep(30)


@pytest.fixture
def plugin_manager():
    # Start from a fresh instance, an earlier one may still be alive
    with suppress(KeyError):
        SingletonMeta.detach_instance("PluginManager")
    pm = PluginManager()

    yield pm

    SingletonMeta.detach_instance("PluginManager")


class TestCurrentApp:
    def test_current_app(self, config: ConfigDict):
        """Test the current_app object properties and immutability.

        Verifies that:
        - The config matches the current_app's config
        - Directory paths are correctly set in current_app
        - The config is immutable (raises AttributeError on modification)
        """
        assert config == current_app.config
        assert Path(config["DIR"]) == current_app.base_dir
        assert Path(config["LOG_DIR"]) == current_app.log_dir
        assert Path(config["CACHE_DIR"]) == current_app.cache_dir

        with pytest.raises(AttributeError):
            current_app.config["TEST_SET"] = None


@pytest.mark.asyncio
class TestFunctionality:
    async def test_functionality_lifecycle(self, config: ConfigDict):
        """Test the complete lifecycle of a Functionality instance.

        Verifies:
        - Proper initialization of the functionality
        - Successful startup sequence (initialize → startup)
        - Proper shutdown sequence (shutdown → post_shutdown)
        - Error handling for double startup/shutdown attempts
        """

        class MockFunctionality(Functionality):
            """Test implementation of Functionality for testing lifecycle methods."""

            def __init__(self, config, **kwargs):
                super().__init__(config, **kwargs)
                self.cleaned_up = False
                self.initialized = False
                self.post_shutdown_called = False

            async def initialize(self) -> None:
                """Mark initialization as complete."""
                self.initialized = True

            async def startup(self) -> None:
                """Mark startup as complete."""
                pass

            async def shutdown(self) -> None:
                """Mark shutdown as complete."""
                self.cleaned_up = True

            async def post_shutdown(self) -> None:
                """Mark post-shutdown as complete."""
                self.post_shutdown_called = True

        func = MockFunctionality(config)

        # Test complete_startup
        await func.complete_startup()
        assert func.initialized
        assert func.started
        assert func.common_resources_state.used_by == 1

        # Test double startup
        with pytest.raises(RuntimeError):
            await func.complete_startup()

        # Test complete_shutdown
        await func.complete_shutdown()
        assert func.cleaned_up
        assert func.post_shutdown_called
        assert not func._status
        assert func.common_resources_state.used_by == 0

        # Test double shutdown
        with pytest.raises(RuntimeError):
            await func.complete_shutdown()


@pytest.mark.asyncio
class TestPlugin:
    @staticmethod
    def _poll_value(manager_dict, expected, timeout: float = 10.0):
        end: float = monotonic() + timeout

        # Use `get` as manager_dict is set up once the subprocess is running for
        # `_SubprocessExecutor`, which might not set "value" in time for the
        # first poll cycle
        while manager_dict.get("value") != expected:
            if monotonic() > end:
                raise TimeoutError
            sleep(0.1)

    async def test_plugin_no_worker(self, config: ConfigDict, dummy_plugin: Plugin):
        """Test plugin operation without worker processes.

        Verifies:
        - Plugin can be started and stopped
        - State is properly maintained in the manager_dict
        - Double startup/shutdown raises appropriate errors
        """
        dummy_plugin.setup_config(config)
        manager_dict = {}
        dummy_plugin.update_kwargs({"manager_dict": manager_dict})

        await dummy_plugin.startup()
        assert isinstance(dummy_plugin.executor, _InProcessExecutor)

        assert manager_dict["value"] == 42

        # Test double startup
        with pytest.raises(RuntimeError):
            await dummy_plugin.startup()

        await dummy_plugin.shutdown()

        assert manager_dict["value"] == 21
        assert not dummy_plugin.is_started
        with pytest.raises(RuntimeError):
            dummy_plugin.executor

        # Test double shutdown
        with pytest.raises(RuntimeError):
            await dummy_plugin.shutdown()

        # Cleanup
        dummy_plugin.kwargs = {}

    async def test_plugin_startup_failure(self, config: ConfigDict):
        """Test that a failed startup leaves the plugin stopped and restartable."""
        class FailingFunctionality(DummyFunctionality):
            fail: bool = True

            async def startup(self):
                if self.fail:
                    raise ValueError("Startup failed")
                await super().startup()

        plugin = Plugin(FailingFunctionality, name="failing", contract_versions={})
        plugin.setup_config(config)
        manager_dict = {}
        plugin.update_kwargs({"manager_dict": manager_dict})

        with pytest.raises(ValueError):
            await plugin.startup()

        assert not plugin.is_started
        with pytest.raises(RuntimeError):
            plugin.executor
        with pytest.raises(RuntimeError):
            await plugin.shutdown()

        # The plugin can be started once the failure is gone
        FailingFunctionality.fail = False
        await plugin.startup()
        assert manager_dict["value"] == 42
        await plugin.shutdown()
        assert not plugin.is_started

    async def test_plugin_worker(self, config: ConfigDict, dummy_plugin: Plugin):
        """Test plugin operation with worker processes.

        Verifies:
        - Plugin can start with worker processes
        - State is properly maintained across process boundaries
        - Processes are properly cleaned up on shutdown
        - Error handling for double operations
        """
        dummy_plugin.setup_config(config)
        dummy_plugin._functionality.workers = 1

        with Manager() as manager:
            manager_dict = manager.dict()
            dummy_plugin.update_kwargs({"manager_dict": manager_dict})

            await dummy_plugin.startup()
            assert isinstance(dummy_plugin.executor, _SubprocessExecutor)
            assert len(dummy_plugin.executor.subprocesses) == 1

            self._poll_value(manager_dict, 42, timeout=10.0)

            # Test double startup
            with pytest.raises(RuntimeError):
                await dummy_plugin.startup()

            await dummy_plugin.shutdown()

            self._poll_value(manager_dict, 21, timeout=10.0)

            # Test double shutdown
            with pytest.raises(RuntimeError):
                await dummy_plugin.shutdown()

        # Cleanup
        dummy_plugin._functionality.workers = 0
        dummy_plugin.kwargs = {}

    async def test_plugin_multiple_workers(self, config: ConfigDict, dummy_plugin: Plugin):
        """Test plugin operation with two worker processes.

        Verifies:
        - Plugin can start with more than one worker
        """
        dummy_plugin.setup_config(config)
        dummy_plugin._functionality.workers = 2

        with Manager() as manager:
            manager_dict = manager.dict()
            dummy_plugin.update_kwargs({"manager_dict": manager_dict})

            await dummy_plugin.startup()
            assert isinstance(dummy_plugin.executor, _SubprocessExecutor)
            assert len(dummy_plugin.executor.subprocesses) == 2

            self._poll_value(manager_dict, 42, timeout=10.0)

            # Test double startup
            with pytest.raises(RuntimeError):
                await dummy_plugin.startup()

            await dummy_plugin.shutdown()

            self._poll_value(manager_dict, 21, timeout=10.0)

            # Test double shutdown
            with pytest.raises(RuntimeError):
                await dummy_plugin.shutdown()

        # Cleanup
        dummy_plugin._functionality.workers = 0
        dummy_plugin.kwargs = {}

    async def test_subprocess_executor_kills_stuck_worker(
            self, config: ConfigDict, caplog: pytest.LogCaptureFixture):
        """Test that a worker ignoring SIGTERM is killed and reaped on stop."""
        executor = _SubprocessExecutor(
            DummyFunctionality, 1, config, logging.getLogger("test-executor"))
        ready = spawn.Event()
        process = spawn.Process(
            target=_ignore_sigterm, args=(ready,), daemon=True, name="stucky")
        process.start()
        # Wait for the process to start
        assert ready.wait(timeout=10.0)
        executor._subprocesses = [process]

        with caplog.at_level(logging.WARNING, logger="test-executor"):
            await executor._stop_processes(0.1)

        assert not process.is_alive()
        # Joined, so not a zombie, and killed rather than terminated
        assert process.exitcode == -signal.SIGKILL
        assert "Process stucky did not terminate cleanly" in caplog.text

    async def test_plugin_with_routes(self, config: ConfigDict):
        """Test plugin route registration.

        Verifies:
        - Routes can be provided during plugin creation
        - Additional routes can be added after creation
        - Route management methods work as expected
        """

        router = APIRouter()

        @router.get("/a_first_one")
        async def a_first_one():
            """Test endpoint that returns a success status."""
            return {"status": "first"}

        plugin = Plugin(
            functionality=DummyFunctionality,
            name="test-plugin",
            contract_versions={},
            routes=[("/api", router)],
        )

        assert plugin.has_route()
        assert len(plugin.routes) == 1

        # Test adding a route
        new_router = APIRouter()

        @new_router.get("/another_one")
        async def another_one():
            """Another test endpoint that returns a success status."""
            return {"status": "second"}

        plugin.add_route(("/api", new_router))
        assert len(plugin.routes) == 2

    @pytest.mark.asyncio
    async def test_plugin_with_cli(self, config: ConfigDict, monkeypatch):
        """Test plugin CLI command integration.

        Verifies:
        - CLI commands can be registered with the plugin
        - Commands are properly invoked
        - Command output is as expected
        """

        # Create a test command
        @click.command("test-cli")
        def test_command():
            """Test command that prints a message."""
            click.echo("Test command executed")

        plugin = Plugin(
            functionality=DummyFunctionality,
            name="test-cli-plugin",
            contract_versions={},
            command=test_command,
            description="Test plugin with CLI command",
        )

        assert plugin.has_command()
        assert plugin.command.name == "test-cli"

        # Test running the command
        result = CliRunner().invoke(plugin.command)
        assert result.exit_code == 0
        assert "Test command executed" in result.output

    async def test_plugin_config_override(self, config: ConfigDict):
        """Test plugin configuration override functionality.

        Verifies:
        - Configuration can be overridden during setup
        - The functionality instance receives the overridden config
        - The original config remains unchanged
        """
        config = ConfigHelper.get_config()
        ConfigHelper._config = None

        plugin = Plugin(
            functionality=DummyFunctionality,
            name="config-plugin",
            contract_versions={},
        )

        # Test with config override
        config_override = {"CUSTOM_CONFIG": "test_value"}
        plugin.setup_config(config, config_override)

        # Verify config is properly set
        assert plugin.config is not None
        assert plugin.config.get("CUSTOM_CONFIG") == "test_value"

        # Test functionality gets the config
        await plugin.startup()
        assert plugin.executor.instance.config.get("CUSTOM_CONFIG") == "test_value"
        await plugin.shutdown()

        ConfigHelper._config = config

    async def test_plugin_manager(self, dummy_plugin: Plugin, plugin_manager: PluginManager):
        """Test the PluginManager functionality.

        Verifies:
        - Plugins are properly registered
        - Plugin lifecycle methods work through the manager
        - Plugin retrieval works as expected
        - Error conditions are properly handled
        """
        plugin_manager.register_plugins()

        assert plugin_manager.plugins["dummy"].name == dummy_plugin.name

        await plugin_manager.start_plugins()
        with pytest.raises(RuntimeError):
            await plugin_manager.start_plugins()

        # Test getting a plugin
        plugin = plugin_manager.get_plugin("dummy")
        assert plugin is not None
        assert plugin.name == "dummy"

        # Test getting non-existent plugin
        assert plugin_manager.get_plugin("non-existent") is None

        await plugin_manager.stop_plugins()

    async def test_manager_registers_routes_only_extension(
            self,
            plugin_manager: PluginManager,
    ):
        """A routes-only `Extension` is registered and its routes are mounted.

        `Extension` is the base of `Plugin`: it carries contract versions and
        routes but no functionality. An entry point resolving to a bare
        `Extension` must still be registered and have its routes reach the API
        router, exactly like a `Plugin` that ships routes.
        """
        async def _ping(request):
            return JSONResponse({"pong": True})

        extension = Extension(
            name="dummy",
            contract_versions={},
            routes=[Route("/ping", _ping)],
        )

        plugin_manager._entry_points = {
            "dummy": SimpleNamespace(name="dummy", load=lambda: extension),
        }
        plugin_manager.register_plugins()

        # Registered and retrievable even though it is not a `Plugin`
        assert plugin_manager.plugins["dummy"] is extension
        assert plugin_manager.get_plugin("dummy") is extension

        # Its routes reach the API router
        main_router = APIRouter()
        plugin_manager.register_plugins_routes(main_router)
        # The plugin name is automatically added as a prefix
        assert any(route.path == "/dummy/ping" for route in main_router.routes)

    async def test_start_plugins_skips_routes_only_extension(
            self,
            plugin_manager: PluginManager,
    ):
        """`start_plugins()` / `stop_plugins()` step over a routes-only `Extension`.

        An `Extension` has no functionality to start, so the lifecycle sweep
        must skip it rather than raise on the missing functionality (which
        would abort the startup of every plugin registered after it).
        """
        extension = Extension(name="dummy", contract_versions={})

        plugin_manager._entry_points = {
            "dummy": SimpleNamespace(name="dummy", load=lambda: extension),
        }
        plugin_manager.register_plugins()
        assert plugin_manager.plugins["dummy"] is extension

        await plugin_manager.start_plugins()
        await plugin_manager.stop_plugins()

    async def test_start_plugins_failure_stops_started_plugins(
            self,
            config: ConfigDict,
            plugin_manager: PluginManager,
    ):
        """`start_plugins()` starts every plugin or none of them.

        When a plugin fails to start, the ones started before it are stopped
        and the error is raised, so the caller knows the startup failed.
        """
        class FailingFunctionality(DummyFunctionality):
            async def startup(self):
                raise ValueError("Startup failed")

        # A first working plugin
        manager_dict_first = {}
        first = Plugin(DummyFunctionality, name="first", contract_versions={})
        first.update_kwargs({"manager_dict": manager_dict_first})
        # The failing plugin
        failing = Plugin(FailingFunctionality, name="failing", contract_versions={})
        # An unreached working plugin
        manager_dict_last = {}
        last = Plugin(DummyFunctionality, name="last", contract_versions={})
        last.update_kwargs({"manager_dict": manager_dict_last})
        # Store everything
        plugin_manager._plugins = {"first": first, "failing": failing, "last": last}

        with pytest.raises(ValueError):
            await plugin_manager.start_plugins()

        assert not first.is_started
        assert manager_dict_first["value"] == 21  # `first` was shut down
        assert not failing.is_started
        assert not last.is_started
        assert not manager_dict_last  # Never reached

    async def test_stop_plugins_continues_after_failure(
            self,
            config: ConfigDict,
            plugin_manager: PluginManager,
            caplog: pytest.LogCaptureFixture,
    ):
        """A plugin failing to stop doesn't leave the others running."""
        class FailingFunctionality(DummyFunctionality):
            async def shutdown(self):
                raise ValueError("Shutdown failed")

        failing = Plugin(FailingFunctionality, name="failing", contract_versions={})
        other = Plugin(DummyFunctionality, name="other", contract_versions={})
        # Plugins are stopped in reverse order: `failing` is stopped first
        plugin_manager._plugins = {"other": other, "failing": failing}

        await plugin_manager.start_plugins()
        with caplog.at_level(logging.ERROR, logger="ouranos.plugin_manager"):
            await plugin_manager.stop_plugins()

        assert not failing.is_started
        assert not other.is_started
        assert "Failed to stop plugin 'failing'" in caplog.text

    async def test_register_plugins_skip_failing_entry_point(
            self,
            dummy_plugin: Plugin,
            plugin_manager: PluginManager,
            caplog: pytest.LogCaptureFixture,
    ):
        """A plugin that fails to load is logged and skipped, not raised.

        `register_plugins` loads every needed entry point in one pass, so a
        single broken plugin (bad contract, import error, ...) must not
        prevent the others from being registered.
        """
        def _raise():
            raise RuntimeError("boom")

        plugin_manager._entry_points = {
            "dummy": SimpleNamespace(name="dummy", load=_raise),
        }

        with caplog.at_level(logging.ERROR, logger="ouranos.plugin_manager"):
            plugin_manager.register_plugins()

        assert "dummy" not in plugin_manager.plugins
        assert "Failed to register plugin 'dummy'" in caplog.text

    async def test_load_plugin_failure_name_mismatch(
            self,
            dummy_plugin: Plugin,
            plugin_manager: PluginManager,
    ):
        """`load_plugin` raises if the entry point and plugin names differ.

        Entry points are keyed by the name declared in `pyproject.toml`, but
        the loaded `Plugin` carries its own `name`. The two must match, or
        the plugin would be registered under one name and behave (routes,
        logs, `plugin.name` lookups) under another.
        """
        plugin_manager._entry_points = {
            "not-dummy": SimpleNamespace(name="not-dummy", load=lambda: dummy_plugin),
        }

        with pytest.raises(ValueError, match="don't match"):
            plugin_manager.load_plugin("not-dummy")

    async def test_load_plugin_failure_point_wrong_type(self, plugin_manager: PluginManager):
        """`load_plugin` raises if the entry point doesn't resolve to a `Plugin`."""
        plugin_manager._entry_points = {
            "dummy": SimpleNamespace(name="dummy", load=lambda: object()),
        }

        with pytest.raises(ValueError, match="does not contain a plugin"):
            plugin_manager.load_plugin("dummy")

    async def test_load_plugin_propagates_failure(self, plugin_manager: PluginManager):
        """Unlike `register_plugins`, `load_plugin` raises on a broken entry point.

        It is an explicit request for one named plugin, so it should fail
        loudly rather than silently skip it.
        """
        def _raise():
            raise RuntimeError("boom")

        plugin_manager._entry_points = {
            "dummy": SimpleNamespace(name="dummy", load=_raise),
        }

        with pytest.raises(RuntimeError, match="boom"):
            plugin_manager.load_plugin("dummy")

    async def test_contract_versions_failure_incompatible(self):
        """Creating a plugin with an unmet contract raises ContractVersionError.

        Two ways to be incompatible: a version Ouranos-core does not provide,
        and a contract name it does not know about.
        """
        # Requires a newer REST contract than Ouranos-core provides
        with pytest.raises(ContractVersionError):
            Plugin(
                functionality=DummyFunctionality,
                name="contract-mismatch-plugin",
                contract_versions={"rest": consts.REST_CONTRACT + 1},
            )

        # Requires a contract Ouranos-core does not expose
        with pytest.raises(ContractVersionError):
            Plugin(
                functionality=DummyFunctionality,
                name="contract-unknown-plugin",
                contract_versions={"unknown": 1},
            )

    async def test_contract_versions(self):
        """A plugin whose required contract versions match Ouranos-core's is created.

        Passing the actual `consts` values (rather than literals) keeps the test
        green across future bumps of the contract numbers.
        """
        plugin = Plugin(
            functionality=DummyFunctionality,
            name="contract-ok-plugin",
            contract_versions={
                "rest": consts.REST_CONTRACT,
                "socketio": consts.SOCKETIO_CONTRACT,
            },
        )

        assert plugin.name == "contract-ok-plugin"
