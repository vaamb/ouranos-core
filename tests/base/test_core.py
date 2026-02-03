from multiprocessing import Manager
from pathlib import Path
from time import sleep
import click
from click.testing import CliRunner
import pytest
from fastapi import APIRouter

from ouranos import current_app
from ouranos.core.config import ConfigDict, ConfigHelper
from ouranos.core.plugins_manager import PluginManager
from ouranos.sdk.plugin import Functionality, Plugin
from ouranos.sdk.tests.plugin import DummyFunctionality


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
        assert func._status

        # Test double startup
        with pytest.raises(RuntimeError):
            await func.complete_startup()

        # Test complete_shutdown
        await func.complete_shutdown()
        assert func.cleaned_up
        assert func.post_shutdown_called
        assert not func._status

        # Test double shutdown
        with pytest.raises(RuntimeError):
            await func.complete_shutdown()


@pytest.mark.asyncio
class TestPlugin:
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
        assert dummy_plugin.instance
        assert not dummy_plugin.has_subprocesses()

        assert manager_dict["value"] == 42

        # Test double startup
        with pytest.raises(RuntimeError):
            await dummy_plugin.startup()

        await dummy_plugin.shutdown()

        assert manager_dict["value"] is None

        # Test double shutdown
        with pytest.raises(RuntimeError):
            await dummy_plugin.shutdown()

        # Cleanup
        dummy_plugin.kwargs = {}

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
            assert dummy_plugin.has_subprocesses()
            assert len(dummy_plugin._subprocesses) == 1

            sleep(2)  # Allow the subprocess to start
            assert manager_dict["value"] == 42

            # Test double startup
            with pytest.raises(RuntimeError):
                await dummy_plugin.startup()

            await dummy_plugin.shutdown()

            sleep(2)  # Allow the subprocess to shut down
            assert manager_dict["value"] is None

            # Test double shutdown
            with pytest.raises(RuntimeError):
                await dummy_plugin.shutdown()

        # Cleanup
        dummy_plugin._functionality.workers = 0
        dummy_plugin.kwargs = {}

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

        plugin = Plugin(functionality=DummyFunctionality, name="config-plugin")

        # Test with config override
        config_override = {"CUSTOM_CONFIG": "test_value"}
        plugin.setup_config(config, config_override)

        # Verify config is properly set
        assert plugin.config is not None
        assert plugin.config.get("CUSTOM_CONFIG") == "test_value"

        # Test functionality gets the config
        await plugin.startup()
        assert plugin.instance.config.get("CUSTOM_CONFIG") == "test_value"
        await plugin.shutdown()

        ConfigHelper._config = config

    async def test_plugin_manager(self, dummy_plugin: Plugin):
        """Test the PluginManager functionality.

        Verifies:
        - Plugins are properly registered
        - Plugin lifecycle methods work through the manager
        - Plugin retrieval works as expected
        - Error conditions are properly handled
        """
        plugin_manager = PluginManager()
        plugin_manager.register_plugins()

        assert plugin_manager.plugins["dummy-plugin"].name == dummy_plugin.name

        await plugin_manager.start_plugins()
        with pytest.raises(RuntimeError):
            await plugin_manager.start_plugins()

        # Test getting a plugin
        plugin = plugin_manager.get_plugin("dummy-plugin")
        assert plugin is not None
        assert plugin.name == "dummy-plugin"

        # Test getting non-existent plugin
        assert plugin_manager.get_plugin("non-existent") is None

        await plugin_manager.stop_plugins()
