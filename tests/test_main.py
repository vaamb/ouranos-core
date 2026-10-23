from contextlib import suppress
from types import SimpleNamespace

import pytest

from ouranos.core.config import ConfigDict
from ouranos.core.plugins_manager import PluginManager
from ouranos.core.utils import SingletonMeta
from ouranos.main import Ouranos
from ouranos.sdk import Extension
from ouranos.sdk.tests.plugin import dummy_plugin


@pytest.fixture
def plugin_manager():
    # Start from a fresh instance, an earlier one may still be alive
    with suppress(KeyError):
        SingletonMeta.detach_instance("PluginManager")
    pm = PluginManager()

    yield pm

    SingletonMeta.detach_instance("PluginManager")


@pytest.mark.asyncio
class TestOuranos:
    async def test_hosts_registered_plugins(
            self,
            config: ConfigDict,
            plugin_manager: PluginManager,
    ):
        ouranos = Ouranos(config)

        assert plugin_manager.plugins_are_registered
        # Only the dummy plugin is registered while testing
        assert ouranos.plugins == [dummy_plugin]
        assert dummy_plugin.kwargs["microservice"] is False

        await ouranos.startup()
        assert ouranos.started
        assert dummy_plugin.is_started

        await ouranos.shutdown()
        assert not ouranos.started
        assert not dummy_plugin.is_started

        # Cleanup
        dummy_plugin.kwargs = {}

    async def test_skips_routes_only_extension(
            self,
            config: ConfigDict,
            plugin_manager: PluginManager,
    ):
        """A routes-only `Extension` has no functionality to run: `Ouranos`
        must skip it rather than abort the startup of every other plugin."""
        extension = Extension(name="dummy", contract_versions={})
        plugin_manager._entry_points = {
            "dummy": SimpleNamespace(name="dummy", load=lambda: extension),
        }
        plugin_manager.register_plugins()
        assert plugin_manager.plugins["dummy"] is extension

        ouranos = Ouranos(config)
        assert ouranos.plugins == []

        await ouranos.startup()
        await ouranos.shutdown()
