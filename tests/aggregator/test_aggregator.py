import pytest

from ouranos.aggregator.main import Aggregator

@pytest.mark.skip
@pytest.mark.asyncio
async def test_aggregator(config):
    aggregator = Aggregator(config)
    await aggregator.complete_startup()
    with pytest.raises(RuntimeError):
        await aggregator.complete_startup()

    await aggregator.complete_shutdown()

# TODO: add other tests
