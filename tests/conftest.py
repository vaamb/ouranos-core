import asyncio
import sys

import pytest
import pytest_asyncio

from ouranos import Config, db as _db, setup_config
from ouranos.core.config import ConfigDict
from ouranos.core.database.init import create_base_data


@pytest.fixture(scope="session", autouse=True)
def config(tmp_path_factory):
    tmp_path = tmp_path_factory.mktemp("base-dir")

    Config.DIR = str(tmp_path)
    Config.TESTING = True
    Config.SQLALCHEMY_DATABASE_URI = "sqlite+aiosqlite://"
    Config.SQLALCHEMY_BINDS = {
        "app": "sqlite+aiosqlite://",
        "system": "sqlite+aiosqlite://",
        "archive": "sqlite+aiosqlite://",
        "memory": "sqlite+aiosqlite://",
    }
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
