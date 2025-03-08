from __future__ import annotations

import os
from pathlib import Path
from typing import TypedDict


class BaseConfig:
    DEBUG = False
    DEVELOPMENT = False
    TESTING = False

    WORKERS = 0

    DIR = os.environ.get("OURANOS_DIR") or os.getcwd()

    @property
    def LOG_DIR(self) -> str | Path:
        return os.environ.get("OURANOS_LOG_DIR") or os.path.join(self.DIR, "logs")

    @property
    def CACHE_DIR(self) -> str | Path:
        return os.environ.get("OURANOS_CACHE_DIR") or os.path.join(self.DIR, ".cache")

    @property
    def DB_DIR(self) -> str | Path:
        return os.environ.get("OURANOS_DB_DIR") or os.path.join(self.DIR, "DBs")

    @property
    def STATIC_DIR(self) -> str | Path:
        return os.environ.get("OURANOS_STATIC_DIR") or os.path.join(self.DIR, "static")

    @property
    def WIKI_DIR(self) -> str | Path:
        return os.environ.get("OURANOS_STATIC_DIR") or os.path.join(self.STATIC_DIR, "wiki")

    SECRET_KEY = os.environ.get("OURANOS_SECRET_KEY") or "secret_key"

    @property
    def CONNECTION_KEY(self):
        return os.environ.get("OURANOS_CONNECTION_KEY") or self.SECRET_KEY

    # Logging config
    LOG_TO_STDOUT = True
    LOG_TO_FILE = False
    LOG_TO_DB = False

    # Brokers config
    GAIA_COMMUNICATION_URL = os.environ.get("GAIA_COMMUNICATION_URL") or "amqp://"  # amqp://
    DISPATCHER_URL = os.environ.get("OURANOS_DISPATCHER_URL") or "memory://"  # memory:// or amqp://
    SIO_MANAGER_URL = os.environ.get("OURANOS_SIO_MANAGER_URL") or "memory://"  # memory:// or amqp:// or redis://

    # Plugins
    API_UID = os.environ.get("OURANOS_UID") or "base_server"
    API_HOST = os.environ.get("OURANOS_API_HOST", "127.0.0.1")
    API_PORT = os.environ.get("OURANOS_API_PORT", 5000)
    API_WORKERS = os.environ.get("OURANOS_API_WORKERS", 0)
    API_SERVER_RELOAD = False

    AGGREGATOR_HOST = os.environ.get("OURANOS_API_HOST", API_HOST)
    AGGREGATOR_PORT = os.environ.get("OURANOS_AGGREGATOR_PORT", 7191)
    GAIA_PICTURE_TRANSFER_METHOD = "both"  # "broker", "http" or "both"

    PLUGINS_OMITTED = os.environ.get("OURANOS_PLUGINS_OMITTED")

    # Ouranos and Gaia config
    ADMINS = os.environ.get("OURANOS_ADMINS", [])
    RECAP_SENDING_HOUR = 4
    MAX_ECOSYSTEMS = 32
    WEATHER_UPDATE_PERIOD = 5  # in min
    ECOSYSTEM_TIMEOUT = 150  # in sec

    # Data logging
    SENSOR_LOGGING_PERIOD = 10
    SYSTEM_LOGGING_PERIOD = 10
    SYSTEM_UPDATE_PERIOD = 5

    # Data archiving
    ACTUATOR_ARCHIVING_PERIOD = None  # 180
    HEALTH_ARCHIVING_PERIOD = None  # 360
    SENSOR_ARCHIVING_PERIOD = None  # 180
    SYSTEM_ARCHIVING_PERIOD = None  # 90
    WARNING_ARCHIVING_PERIOD = None  # 90

    # SQLAlchemy config
    @property
    def SQLALCHEMY_DATABASE_URI(self) -> str | Path:
        return (
            os.environ.get("OURANOS_DATABASE_URI") or
            "sqlite+aiosqlite:///" + os.path.join(self.DB_DIR, "ecosystems.db")
        )

    @property
    def SQLALCHEMY_BINDS(self) -> dict[str, str | Path]:
        return {
            "app": (os.environ.get("OURANOS_APP_DATABASE_URI") or
                    "sqlite+aiosqlite:///" + os.path.join(self.DB_DIR, "app.db")),
            "system": (os.environ.get("OURANOS_SYSTEM_DATABASE_URI") or
                       "sqlite+aiosqlite:///" + os.path.join(self.DB_DIR, "system.db")),
            "archive": (os.environ.get("OURANOS_ARCHIVE_DATABASE_URI") or
                        "sqlite+aiosqlite:///" + os.path.join(self.DB_DIR, "archive.db")),
            "memory": "sqlite+aiosqlite://",
        }

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_RECORD_QUERIES = True
    SLOW_DB_QUERY_TIME = 0.5
    SQLALCHEMY_ECHO = False

    # Mail config
    MAIL_SERVER = os.environ.get("OURANOS_MAIL_SERVER") or "smtp.gmail.com"
    MAIL_PORT = int(os.environ.get("OURANOS_MAIL_PORT") or 465)
    MAIL_USE_TLS = True
    MAIL_USERNAME = os.environ.get("OURANOS_MAIL_ADDRESS")
    MAIL_PASSWORD = os.environ.get("OURANOS_MAIL_PASSWORD")
    MAIL_SENDER_ADDRESS = os.environ.get("OURANOS_MAIL_SENDER_ADDRESS")

    # Private parameters
    HOME_CITY = os.environ.get("HOME_CITY")
    HOME_COORDINATES = os.environ.get("HOME_COORDINATES")
    OPEN_WEATHER_MAP_API_KEY = os.environ.get("DARKSKY_API_KEY")
    WEATHER_REFRESH_INTERVAL = 15  # in minute


class BaseConfigDict(TypedDict):
    # Reserved parameters
    APP_NAME: str
    VERSION: str

    DEBUG: bool
    DEVELOPMENT: bool
    TESTING: bool

    WORKERS: int | None

    DIR: str | Path
    LOG_DIR: str | Path
    CACHE_DIR: str | Path
    DB_DIR: str | Path
    STATIC_DIR: str | Path
    WIKI_DIR: str | Path

    SECRET_KEY: str
    CONNECTION_KEY: str

    # Logging config
    LOG_TO_STDOUT: bool
    LOG_TO_FILE: bool
    LOG_TO_DB: bool

    # Brokers config
    GAIA_COMMUNICATION_URL: str
    DISPATCHER_URL: str
    SIO_MANAGER_URL: str

    # Plugins
    API_UID: str
    API_HOST: str
    API_PORT: int
    API_WORKERS: int
    API_SERVER_RELOAD: bool

    AGGREGATOR_HOST: str
    AGGREGATOR_PORT: int
    GAIA_PICTURE_TRANSFER_METHOD: str

    PLUGINS_OMITTED: str

    # Ouranos and Gaia config
    ADMINS: list[str]
    RECAP_SENDING_HOUR: int | None
    MAX_ECOSYSTEMS: int
    WEATHER_UPDATE_PERIOD: int
    ECOSYSTEM_TIMEOUT: int

    # Data logging
    SENSOR_LOGGING_PERIOD: int | None
    SYSTEM_LOGGING_PERIOD: int | None
    SYSTEM_UPDATE_PERIOD: int | None

    # Data archiving
    ACTUATOR_ARCHIVING_PERIOD: int | None
    HEALTH_ARCHIVING_PERIOD: int | None
    SENSOR_ARCHIVING_PERIOD: int | None
    SYSTEM_ARCHIVING_PERIOD: int | None
    WARNING_ARCHIVING_PERIOD: int | None

    # SQLAlchemy config
    SQLALCHEMY_DATABASE_URI: str | Path
    SQLALCHEMY_BINDS: dict[str, str | Path]

    SQLALCHEMY_TRACK_MODIFICATIONS: bool
    SQLALCHEMY_RECORD_QUERIES: bool
    SLOW_DB_QUERY_TIME: float
    SQLALCHEMY_ECHO: bool

    # Mail config
    MAIL_SERVER: str
    MAIL_PORT: int
    MAIL_USE_TLS: bool
    MAIL_USERNAME: str | None
    MAIL_PASSWORD: str | None
    MAIL_SENDER_ADDRESS: str | None

    # Private parameters
    HOME_CITY: str | None
    HOME_COORDINATES: tuple[float, float] | None
    OPEN_WEATHER_MAP_API_KEY: str | None
    WEATHER_REFRESH_INTERVAL: int
