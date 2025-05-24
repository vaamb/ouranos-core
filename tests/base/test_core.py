from multiprocessing import Manager
from pathlib import Path
from time import sleep

import pytest

from ouranos import current_app
from ouranos.core.config import ConfigDict
from ouranos.core.plugins_manager import PluginManager
from ouranos.sdk.plugin import Plugin
from ouranos.sdk.tests.plugin import DummyFunctionality


def test_current_app(config: ConfigDict):
    assert config == current_app.config
    assert Path(config["DIR"]) == current_app.base_dir
    assert Path(config["LOG_DIR"]) == current_app.log_dir
    assert Path(config["CACHE_DIR"]) == current_app.cache_dir


@pytest.mark.asyncio
async def test_functionality(config: ConfigDict):
    functionality = DummyFunctionality(config)
    assert functionality.config == config
    await functionality.startup()
    with pytest.raises(RuntimeError):
        await functionality.startup()
    await functionality.shutdown()


@pytest.mark.asyncio
async def test_plugin_no_worker(config: ConfigDict, dummy_plugin: Plugin):
    dummy_plugin.setup_config(config)
    manager_dict = {}
    dummy_plugin.kwargs = {"manager_dict": manager_dict}

    await dummy_plugin.start()
    assert dummy_plugin.instance
    assert not dummy_plugin.has_subprocesses()

    assert manager_dict["value"] == 42

    await dummy_plugin.stop()

    assert manager_dict["value"] is None

    # Cleanup
    dummy_plugin.kwargs = {}


@pytest.mark.asyncio
async def test_plugin_worker(config: ConfigDict, dummy_plugin: Plugin):
    dummy_plugin.setup_config(config)
    dummy_plugin._functionality.workers = 1

    with Manager() as manager:
        manager_dict = manager.dict()
        dummy_plugin.kwargs = {"manager_dict": manager_dict}

        await dummy_plugin.start()
        assert not dummy_plugin.instance
        assert dummy_plugin.has_subprocesses()
        assert len(dummy_plugin._subprocesses) == 1

        sleep(2)  # Allow the subprocess to start and the functionality to init
        assert manager_dict["value"] == 42

        await dummy_plugin.stop()

        sleep(2)
        assert manager_dict["value"] is None

    dummy_plugin._functionality.workers = 0

    # Cleanup
    dummy_plugin.kwargs = {}


@pytest.mark.asyncio
async def test_plugin_manager(dummy_plugin: Plugin):
    plugin_manager = PluginManager()
    plugin_manager.register_plugins()

    assert(plugin_manager.plugins["dummy-plugin"].name == dummy_plugin.name)

    await plugin_manager.start_plugins()
    with pytest.raises(RuntimeError):
        await plugin_manager.start_plugins()
    await plugin_manager.stop_plugins()
