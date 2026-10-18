import pytest

from ouranos.aggregator.main import Aggregator
from ouranos.core.config import ConfigDict
from ouranos.core.globals import scheduler


@pytest.mark.asyncio
class TestAggregator:
    async def test_lifecycle(self, config: ConfigDict):
        """Test the complete lifecycle of an Aggregator instance.

        Verifies:
        - Proper initialization of the functionality
        - Successful startup sequence (initialize → startup)
        - Proper shutdown sequence (shutdown → post_shutdown)
        - Error handling for double startup/shutdown attempts
        """

        aggregator = Aggregator(config)

        # Ensure dispatcher-related properties raise after initialization
        with pytest.raises(RuntimeError):
            assert aggregator.gaia_dispatcher
        with pytest.raises(RuntimeError):
            assert aggregator.stream_dispatcher
        with pytest.raises(RuntimeError):
            assert aggregator.internal_dispatcher
        with pytest.raises(RuntimeError):
            assert aggregator.event_handler

        # Test complete_startup
        await aggregator.complete_startup()
        assert aggregator.started
        assert aggregator.common_resources_state.used_by == 1

        # Ensure dispatcher-related properties are now valid
        assert aggregator.gaia_dispatcher is not None
        assert aggregator.stream_dispatcher is not None
        assert aggregator.internal_dispatcher is not None
        assert aggregator.event_handler is not None

        # Test double startup
        with pytest.raises(RuntimeError):
            await aggregator.complete_startup()

        # Test complete_shutdown
        await aggregator.complete_shutdown()
        assert not aggregator.started
        assert aggregator.common_resources_state.used_by == 0

        # Ensure dispatcher-related properties raise after shutdown
        with pytest.raises(RuntimeError):
            assert aggregator.gaia_dispatcher
        with pytest.raises(RuntimeError):
            assert aggregator.stream_dispatcher
        with pytest.raises(RuntimeError):
            assert aggregator.internal_dispatcher
        with pytest.raises(RuntimeError):
            assert aggregator.event_handler

        # Test double shutdown
        with pytest.raises(RuntimeError):
            await aggregator.complete_shutdown()

    async def test_shutdown_failing_component(
            self,
            config: ConfigDict,
            monkeypatch: pytest.MonkeyPatch,
    ):
        """A component failing to stop must not prevent the others from stopping."""
        aggregator = Aggregator(config)
        await aggregator.complete_startup()
        dispatchers = (
            aggregator.gaia_dispatcher,
            aggregator.internal_dispatcher,
            aggregator.stream_dispatcher,
        )

        async def failing_stop() -> None:
            raise RuntimeError("Archiver failed to stop")

        monkeypatch.setattr(aggregator.archiver, "stop", failing_stop)

        await aggregator.complete_shutdown()
        assert not aggregator.started
        # The dispatchers, stopped after the archiver, are stopped nonetheless
        assert not any(dispatcher.running for dispatcher in dispatchers)
        assert scheduler.get_job("log_sensors_data_and_alarms") is None
