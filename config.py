import os

from ouranos import Config


class DevelopmentConfig(Config):
    DEBUG = True
    DEVELOPMENT = True
    MAIL_DEBUG = True


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite+aiosqlite:///"
    SQLALCHEMY_BINDS = {
        "app": "sqlite+aiosqlite:///",
        "archive": "sqlite+aiosqlite:///",
        "system": "sqlite+aiosqlite:///",
    }


class ProductionConfig(Config):
    DEBUG = False
    TESTING = False

    LOG_TO_STDOUT = False

    SQLALCHEMY_DATABASE_URI = os.environ.get("OURANOS_DATABASE_URI")
    SQLALCHEMY_BINDS = {
        "app": os.environ.get("OURANOS_APP_DATABASE_URI"),
        "system": os.environ.get("OURANOS_SYSTEM_DATABASE_URI"),
        "archive": os.environ.get("OURANOS_ARCHIVE_DATABASE_URI"),
    }


DEFAULT_CONFIG = DevelopmentConfig
