import asyncio
import os
import shutil
import tempfile
import typing as t

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import select

from .utils import user, operator, admin
from src.app import create_app
from src.database.wrapper import AsyncSQLAlchemyWrapper
from src.database.models.app import Role, User
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
def app():
    temp_directory = tempfile.mkdtemp(suffix="gaiaWeb")
    config = patch_config(TestingConfig, temp_directory)
    app = create_app(config)
    db: AsyncSQLAlchemyWrapper = app.extra["db"]

    async def create_fake_users():
        async with db.scoped_session() as session:
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

    try:
        yield app
    finally:
        try:
            shutil.rmtree(temp_directory)
        except PermissionError:
            # Raised in Windows although the directory is effectively deleted
            pass


@pytest.fixture()
def client(app):
    client = TestClient(app)
    yield client
