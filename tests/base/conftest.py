import pytest

from ouranos.sdk.plugin import Plugin
from ouranos.sdk.tests.plugin import DummyFunctionality


@pytest.fixture(scope="function")
def dummy_plugin():
    return Plugin(
        functionality=DummyFunctionality,
        name="dummy-plugin",
    )
