import os

from ouranos import Config


class PlugInConfig(Config):
    TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")


class DevelopmentConfig(PlugInConfig):
    DEBUG = True
    DEVELOPMENT = True
    MAIL_DEBUG = True


class TestingConfig(PlugInConfig):
    TESTING = True

    DISPATCHER_URL = os.environ.get("OURANOS_DISPATCHER_URL") or "amqp://"

    SQLALCHEMY_DATABASE_URI = "sqlite+aiosqlite:///"
    SQLALCHEMY_BINDS = {
        "app": "sqlite+aiosqlite:///",
        "archive": "sqlite+aiosqlite:///",
        "system": "sqlite+aiosqlite:///",
    }


class ProductionConfig(PlugInConfig):
    DEBUG = False
    TESTING = False

    LOG_TO_STDOUT = False

    DISPATCHER_URL = os.environ.get("OURANOS_DISPATCHER_URL") or "amqp://"

    SQLALCHEMY_DATABASE_URI = os.environ.get("OURANOS_DATABASE_URI")
    SQLALCHEMY_BINDS = {
        "app": os.environ.get("OURANOS_APP_DATABASE_URI"),
        "system": os.environ.get("OURANOS_SYSTEM_DATABASE_URI"),
        "archive": os.environ.get("OURANOS_ARCHIVE_DATABASE_URI"),
    }


DEFAULT_CONFIG = DevelopmentConfig
