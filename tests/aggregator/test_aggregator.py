import pytest

from ouranos.aggregator.main import Aggregator


@pytest.mark.asyncio
async def test_aggregator(config):
    aggregator = Aggregator(config)
    await aggregator.startup()
    with pytest.raises(RuntimeError):
        await aggregator.startup()

    await aggregator.shutdown()

# TODO: add other tests
