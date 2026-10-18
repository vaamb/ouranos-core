import asyncio

import pytest

from ouranos.core.config import ConfigDict
from ouranos.main import Ouranos


class MockOuranos(Ouranos):
    """`Ouranos` without its plugins, failing on demand."""

    def __init__(self, config: ConfigDict, *, fail_with: BaseException | None = None):
        super().__init__(config)
        self.fail_with = fail_with

    async def startup(self) -> None:
        if self.fail_with is not None:
            raise self.fail_with

    async def shutdown(self) -> None:
        if self.fail_with is not None:
            raise self.fail_with


@pytest.mark.asyncio
class TestOuranos:
    async def test_lifecycle(self, config: ConfigDict):
        ouranos = MockOuranos(config)

        await ouranos.complete_startup()
        assert ouranos.started
        assert ouranos.common_resources_state.used_by == 1

        await ouranos.complete_shutdown()
        assert not ouranos.started
        assert ouranos.common_resources_state.used_by == 0

    async def test_startup_failure_releases_common_resources(self, config: ConfigDict):
        ouranos = MockOuranos(config, fail_with=ValueError("plugin failed"))

        with pytest.raises(ValueError):
            await ouranos.complete_startup()
        assert not ouranos.started
        assert ouranos.common_resources_state.used_by == 0

    async def test_cancelled_shutdown_still_stops(self, config: ConfigDict):
        ouranos = MockOuranos(config)
        await ouranos.complete_startup()

        ouranos.fail_with = asyncio.CancelledError()
        await ouranos.complete_shutdown()
        assert not ouranos.started
        assert ouranos.common_resources_state.used_by == 0
