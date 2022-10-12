from __future__ import annotations

from pathlib import Path
import os
import typing as t


try:
    from private_config import privateConfig
except ImportError:  # noqa
    class privateConfig:
        ADMIN = None
        REGISTRATION_KEY = "BXhNmCEmNdoBNngyGXj6jJtooYAcKpt6"
        HOME_CITY = "Somewhere over the rainbow"
        HOME_COORDINATES = (0.0, 0.0)
        DARKSKY_API_KEY = None
        TELEGRAM_BOT_TOKEN = None
        MAIL_USERNAME = None
        MAIL_PASSWORD = None


default_profile = os.environ.get("CONFIG_PROFILE") or "development"

base_dir = Path(__file__).absolute().parents[0]  # TODO: use the one from g?


class Config:
    APP_NAME = "Ouranos"
    VERSION = "0.5.3"
    DIR = None
    DEBUG = False
    TESTING = False
    SECRET_KEY = os.environ.get("SECRET_KEY") or "BXhNmCEmNdoBNngyGXj6jJtooYAcKpt6"
    JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY") or SECRET_KEY
    WORKERS = 1

    # Logging config
    LOG_TO_STDOUT = True
    LOG_TO_FILE = True
    LOG_ERROR = True

    # Ouranos and Gaia config
    TEST_CONNECTION_IP = "1.1.1.1"
    OURANOS_ADMIN = os.environ.get("OURANOS_ADMIN") or privateConfig.ADMIN
    OURANOS_REGISTRATION_KEY = os.environ.get("OURANOS_REGISTRATION_KEY") or \
        privateConfig.REGISTRATION_KEY
    OURANOS_RECAP_SENDING_HOUR = 4
    OURANOS_MAX_ECOSYSTEMS = 32
    OURANOS_WEATHER_UPDATE_PERIOD = 5  # in min
    GAIA_ECOSYSTEM_TIMEOUT = 150
    GAIA_SECRET_KEY = os.environ.get("GAIA_SECRET_KEY") or SECRET_KEY

    # SQLAlchemy config
    SQLALCHEMY_DATABASE_URI = (
            os.environ.get("ECOSYSTEM_DATABASE_URI") or
            "sqlite+aiosqlite:///" + os.path.join(base_dir, "db_ecosystems.db")
    )
    SQLALCHEMY_BINDS = {
        "app": (os.environ.get("APP_DATABASE_URI") or
                "sqlite+aiosqlite:///" + os.path.join(base_dir, "db_app.db")),
        "system": (os.environ.get("SYSTEM_DATABASE_URI") or
                   "sqlite+aiosqlite:///" + os.path.join(base_dir, "db_system.db")),
        "archive": (os.environ.get("ARCHIVE_DATABASE_URI") or
                    "sqlite+aiosqlite:///" + os.path.join(base_dir, "db_archive.db"))
    }
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_RECORD_QUERIES = True
    SLOW_DB_QUERY_TIME = 0.5
    SQLALCHEMY_ECHO = False

    # Mail config
    MAIL_SERVER = os.environ.get("MAIL_SERVER") or "smtp.gmail.com"
    MAIL_PORT = int(os.environ.get("MAIL_PORT") or 465)
    MAIL_USE_TLS = False
    MAIL_USE_SSL = True
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME") or privateConfig.MAIL_USERNAME
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD") or privateConfig.MAIL_PASSWORD
    MAIL_SUPPRESS_SEND = False

    # Dispatcher config
    USE_REDIS_DISPATCHER = False
    MESSAGE_BROKER_URL = "amqp://"  # "memory://"
    GAIA_BROKER_URL = "amqp://"  # "socketio://"
    # CACHING_SERVER_URL

    # Data logging
    SYSTEM_LOGGING_PERIOD = 10
    SENSORS_LOGGING_PERIOD = 10
    # TODO: add cache and logs path

    # Private parameters
    HOME_CITY = os.environ.get("HOME_CITY") or privateConfig.HOME_CITY
    HOME_COORDINATES = os.environ.get("HOME_COORDINATES") or privateConfig.HOME_COORDINATES
    DARKSKY_API_KEY = os.environ.get("DARKSKY_API_KEY") or privateConfig.DARKSKY_API_KEY
    TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN") or privateConfig.TELEGRAM_BOT_TOKEN


class DevelopmentConfig(Config):
    DEBUG = False
    TESTING = True
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
    SQLALCHEMY_DATABASE_URI = "mysql://user@localhost/foo"


configs = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}

config_profiles_available = [profile for profile in configs]


def _get_config_class(
        profile: str | None = None
) -> t.Type[DevelopmentConfig | ProductionConfig | TestingConfig]:
    if profile is None or profile.lower() in ("def", "default"):
        return configs[default_profile]
    elif profile.lower() in ("dev", "development"):
        return configs["development"]
    elif profile.lower() in ("test", "testing"):
        return configs["testing"]
    elif profile.lower() in ("prod", "production"):
        return configs["production"]
    else:
        raise ValueError(
            f"{profile} is not a valid profile. Valid profiles are "
            f"{config_profiles_available}."
        )


def config_dict_from_class(obj: t.Type) -> dict[str, str | int | bool]:
    config = {}
    for key in dir(obj):
        if key.isupper():
            config[key] = getattr(obj, key)
    return config


def get_specified_config(profile: str | None = None) -> dict[str, str | int | bool]:
    config_cls = _get_config_class(profile)
    return config_dict_from_class(config_cls)
