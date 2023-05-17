import asyncio
from pathlib import Path
import sys
from typing import Type

import pytest
import pytest_asyncio

from ouranos import Config, db, setup_config
from ouranos.core.config import ConfigDict


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
    config = setup_config(Config)
    yield config


@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_db(config: ConfigDict):
    db.init(config)
    from ouranos.core.database import models  # noqa
    await db.create_all()
    return db
