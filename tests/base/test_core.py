from pathlib import Path

import pytest

from ouranos import current_app
from ouranos.core.config import ConfigDict
from ouranos.core.plugins_manager import PluginManager
from ouranos.sdk.tests.plugin import DummyFunctionality, dummy_plugin


def test_current_app(config: ConfigDict):
    assert config == current_app.config
    assert Path(config["DIR"]) == current_app.base_dir
    assert Path(config["LOG_DIR"]) == current_app.log_dir
    assert Path(config["CACHE_DIR"]) == current_app.cache_dir


@pytest.mark.asyncio
async def test_functionality(config):
    functionality = DummyFunctionality(auto_setup_config=False)
    assert functionality.config == config
    await functionality.startup()
    with pytest.raises(RuntimeError):
        await functionality.startup()
    await functionality.shutdown()


@pytest.mark.asyncio
async def test_plugin_manager():
    plugin_manager = PluginManager()
    plugin_manager.register_plugins()

    assert(plugin_manager.plugins["dummy-plugin"] == dummy_plugin)

    plugin_manager.init_plugins()
    await plugin_manager.start_plugins()
    with pytest.raises(RuntimeError):
        await plugin_manager.start_plugins()
    await plugin_manager.stop_plugins()
