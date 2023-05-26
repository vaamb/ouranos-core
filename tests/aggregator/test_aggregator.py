import pytest

from ouranos.aggregator.main import Aggregator


def test_aggregator(config):
    aggregator = Aggregator(auto_setup_config=False)
    aggregator.startup()
    with pytest.raises(RuntimeError):
        aggregator.startup()

    aggregator.shutdown()

# TODO: add other tests
