from logging import getLogger

import pytest
import pytest_asyncio

from ouranos import Config, db as ouranos_db, setup_config
from ouranos.core.config import ConfigDict
from ouranos.core.database.init import setup_db
from ouranos.core.database.models import caches

from .data.auth import admin


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
        "transient": "sqlite+aiosqlite://",
    }
    Config.SENSOR_LOGGING_PERIOD = 1
    Config.SYSTEM_LOGGING_PERIOD = 1

    Config.FRONTEND_URL = "http://127.0.0.1:42424"
    Config.MAIL_SERVER = "127.0.0.1"
    Config.MAIL_PORT = 465
    Config.MAIL_USERNAME = admin.username
    Config.MAIL_PASSWORD = admin.password

    Config.HOME_COORDINATES = (42, 0)
    Config.OPEN_WEATHER_MAP_API_KEY = "key"

    config = setup_config(Config)
    yield config


@pytest_asyncio.fixture(scope="class", autouse=True)
async def db(config: ConfigDict):
    logger = getLogger("ouranos")
    await setup_db(ouranos_db, config, logger)

    yield ouranos_db

    await ouranos_db.drop_all()

    for engine in ouranos_db.engines.values():
        await engine.dispose()

    # Clear up the caches
    for key, value in caches.__dict__.items():
        if key.startswith("cache_"):
            value.clear()
