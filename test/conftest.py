import os
import shutil
import tempfile

import pytest

from app import create_app, db
from app.models import Service
from config import TestingConfig


SERVICES = {
    "calendar": "app",
    "weather": "app",
    "webcam": "app",
    "daily_recap": "user",
    "telegram_chatbot": "user",
}


def patch_config(ConfigClass, temp_directory):
    """Change database URIs to use a temporary directory"""
    ConfigClass.SQLALCHEMY_DATABASE_URI = (
            "sqlite:///" + os.path.join(temp_directory, "db_ecosystems.db")
    )
    ConfigClass.SQLALCHEMY_BINDS = {
        "app": "sqlite:///" + os.path.join(temp_directory, "db_app.db"),
        "archive": "sqlite:///" + os.path.join(temp_directory, "db_archive.db")
    }
    return ConfigClass


def log_and_enable_services():
    for service in SERVICES:
        s = Service(name=service, level=SERVICES[service], status=1)
        db.session.add(s)
    db.session.commit()


@pytest.fixture(scope="session")
def app():
    temp_directory = tempfile.mkdtemp(suffix="gaiaWeb")
    config = patch_config(TestingConfig, temp_directory)
    app = create_app(config)
    with app.app_context():
        log_and_enable_services()
    try:
        yield app
    finally:
        try:
            shutil.rmtree(temp_directory)
        except PermissionError:
            # Raised in Windows although the directory is effectively deleted
            pass


@pytest.fixture(scope="session")
def client(app):
    ctx = app.app_context()
    ctx.push()
    with app.test_client(use_cookies=True) as client:
        yield client
