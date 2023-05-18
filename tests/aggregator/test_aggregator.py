import pytest

from ouranos.aggregator.main import Aggregator


def test_aggregator(config):
    aggregator = Aggregator(auto_setup_config=False)
    aggregator.start()
    with pytest.raises(RuntimeError):
        aggregator.start()

    aggregator.stop()

# TODO: add other tests
