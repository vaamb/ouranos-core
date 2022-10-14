from __future__ import annotations

from pathlib import Path
import os
import typing as t


default_profile = os.environ.get("OURANOS_CONFIG_PROFILE") or "development"

_base_dir = Path(__file__).absolute().parents[0]


class Config:
    APP_NAME = "Ouranos"
    VERSION = "0.5.3"

    DEBUG = False
    TESTING = False

    DIR = os.environ.get("OURANOS_DIR") or _base_dir
    LOG_DIR = os.environ.get("OURANOS_LOG_DIR")
    CACHE_DIR = os.environ.get("OURANOS_CACHE_DIR")

    SECRET_KEY = os.environ.get("OURANOS_SECRET_KEY") or "secret_key"
    CONNECTION_KEY = os.environ.get("OURANOS_CONNECTION_KEY") or SECRET_KEY

    # Logging config
    LOG_TO_STDOUT = True
    LOG_TO_FILE = True
    LOG_ERROR = True

    # Brokers config
    GAIA_COMMUNICATION_URL = os.environ.get("GAIA_COMMUNICATION_URL") or "amqp://"  # "socketio://"
    DISPATCHER_URL = os.environ.get("OURANOS_DISPATCHER_URL") or "amqp://"
    SIO_MANAGER_URL = os.environ.get("OURANOS_SIO_MANAGER_URL") or "memory://"
    # CACHE_URL = os.environ.get("OURANOS_CACHE_URL") or "memory://"

    # Services
    START_API = os.environ.get("OURANOS_START_API", True)
    API_WORKERS = os.environ.get("OURANOS_API_WORKERS", 1)
    START_AGGREGATOR = os.environ.get("OURANOS_START_AGGREGATOR", True)

    # Ouranos and Gaia config
    ADMINS = os.environ.get("OURANOS_ADMINS")
    RECAP_SENDING_HOUR = 4
    MAX_ECOSYSTEMS = 32
    WEATHER_UPDATE_PERIOD = 5  # in min
    ECOSYSTEM_TIMEOUT = 150  # in sec

    # Data logging
    SYSTEM_LOGGING_PERIOD = 10
    SENSORS_LOGGING_PERIOD = 10

    # SQLAlchemy config
    SQLALCHEMY_DATABASE_URI = (
            os.environ.get("OURANOS_DATABASE_URI") or
            "sqlite+aiosqlite:///" + os.path.join(DIR, "db_ecosystems.db")
    )
    SQLALCHEMY_BINDS = {
        "app": (os.environ.get("OURANOS_APP_DATABASE_URI") or
                "sqlite+aiosqlite:///" + os.path.join(DIR, "db_app.db")),
        "system": (os.environ.get("OURANOS_SYSTEM_DATABASE_URI") or
                   "sqlite+aiosqlite:///" + os.path.join(DIR, "db_system.db")),
        "archive": (os.environ.get("OURANOS_ARCHIVE_DATABASE_URI") or
                    "sqlite+aiosqlite:///" + os.path.join(DIR, "db_archive.db"))
    }
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_RECORD_QUERIES = True
    SLOW_DB_QUERY_TIME = 0.5
    SQLALCHEMY_ECHO = False

    # Mail config
    MAIL_SERVER = os.environ.get("OURANOS_MAIL_SERVER") or "smtp.gmail.com"
    MAIL_PORT = int(os.environ.get("OURANOS_MAIL_PORT") or 465)
    MAIL_USE_TLS = False
    MAIL_USE_SSL = True
    MAIL_USERNAME = os.environ.get("OURANOS_MAIL_ADDRESS")
    MAIL_PASSWORD = os.environ.get("OURANOS_MAIL_PASSWORD")
    MAIL_SUPPRESS_SEND = False

    # Private parameters
    HOME_CITY = os.environ.get("HOME_CITY")
    HOME_COORDINATES = os.environ.get("HOME_COORDINATES")
    DARKSKY_API_KEY = os.environ.get("DARKSKY_API_KEY")
    TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")


class DevelopmentConfig(Config):
    DEBUG = True
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
    DEBUG = False
    TESTING = False

    LOG_TO_STDOUT = False

    SQLALCHEMY_DATABASE_URI = os.environ.get("OURANOS_DATABASE_URI")
    SQLALCHEMY_BINDS = {
        "app": os.environ.get("OURANOS_APP_DATABASE_URI"),
        "system": os.environ.get("OURANOS_SYSTEM_DATABASE_URI"),
        "archive": os.environ.get("OURANOS_ARCHIVE_DATABASE_URI"),
    }


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
