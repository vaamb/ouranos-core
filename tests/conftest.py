import asyncio
import os
import shutil
import tempfile
import typing as t

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import select

from .utils import user, operator, admin
from ouranos.api import create_app, db as _db
from ouranos.core.database.models import Role, User
from config import TestingConfig


SERVICES = {
    "calendar": "app",
    "weather": "app",
    "webcam": "app",
    "daily_recap": "user",
    "telegram_chatbot": "user",
}


def patch_config(config_class: t.Type[TestingConfig], temp_directory):
    """Change database URIs to use a temporary directory"""
    config_class.SQLALCHEMY_DATABASE_URI = (
            "sqlite+aiosqlite:///" + os.path.join(temp_directory, "db_ecosystems.db")
    )
    config_class.SQLALCHEMY_BINDS = {
        "app": "sqlite+aiosqlite:///" + os.path.join(temp_directory, "db_app.db"),
        "archive": "sqlite+aiosqlite:///" + os.path.join(temp_directory, "db_archive.db"),
        "system": "sqlite+aiosqlite:///" + os.path.join(temp_directory, "db_system.db"),
    }
    return config_class


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def temp_dir():
    temp_directory = tempfile.mkdtemp(suffix="gaiaWeb")
    try:
        yield temp_directory
    finally:
        try:
            shutil.rmtree(temp_directory)
        except PermissionError:
            # Raised in Windows although the directory is effectively deleted
            pass


@pytest.fixture(scope="session")
def config(temp_dir):
    config = patch_config(TestingConfig, temp_dir)
    yield config


@pytest.fixture(scope="session")
def db():
    yield _db


@pytest.fixture(scope="session")
def app(config, db):
    # Patch dependencies
    async def patched_session():
        yield db._session_factory()

    get_session = patched_session

    app = create_app(config)

    async def create_fake_users():
        async with db._session() as session:
            for usr in (user, operator, admin):
                stmt = select(Role).where(Role.name == usr.role)
                result = await session.execute(stmt)
                u = User(
                    username=usr.username,
                    firstname=usr.firstname,
                    lastname=usr.lastname,
                    role=result.scalars().first(),
                )
                u.set_password(usr.password)
                session.add(u)
            session.commit()

    asyncio.run(create_fake_users())
    yield app


@pytest.fixture()
def client(app):
    client = TestClient(app)
    yield client
