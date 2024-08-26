import asyncio
from pathlib import Path
import sys

import pytest
import pytest_asyncio

from ouranos import Config, db as _db, setup_config
from ouranos.core.config import ConfigDict
from ouranos.core.database.init import create_base_data


@pytest.fixture(scope="session")
def event_loop():
    if sys.platform.startswith("win") and sys.version_info[:2] >= (3, 8):
        # Avoid "RuntimeError: Event loop is closed" on Windows when tearing down tests
        # https://github.com/encode/httpx/issues/914
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session", autouse=True)
def config(tmp_path_factory):
    tmp_path = tmp_path_factory.mktemp("base-dir")
    Config.DIR = str(tmp_path)
    db_dir = Path(Config().DB_DIR)
    if not db_dir.exists():
        db_dir.mkdir()
    Config.TESTING = True
    Config.SENSOR_LOGGING_PERIOD = 1
    Config.SYSTEM_LOGGING_PERIOD = 1
    config = setup_config(Config)
    _db.init(config)
    yield config


@pytest_asyncio.fixture(scope="module", autouse=True)
async def db(config: ConfigDict):
    from ouranos.core.database import models  # noqa
    from ouranos.core.database.models import caches
    await _db.create_all()
    await create_base_data()
    yield _db
    await _db.drop_all()
    # Clear up the caches
    for key, value in caches.__dict__.items():
        if key.startswith("cache_"):
            value.clear()
