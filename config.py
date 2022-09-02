from pathlib import Path
import os

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


base_dir = Path(__file__).absolute().parents[0]


class Config:
    APP_NAME = "Ouranos"
    VERSION = "0.5.3"
    DIR = None
    DEBUG = False
    TESTING = False
    SECRET_KEY = os.environ.get("SECRET_KEY") or "BXhNmCEmNdoBNngyGXj6jJtooYAcKpt6"
    JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY") or SECRET_KEY

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
    MESSAGE_BROKER_URL = "memory://"
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
    DEBUG = True
    TESTING = True
    MAIL_DEBUG = True


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///"
    SQLALCHEMY_BINDS = {
        "app": "sqlite:///",
        "archive": "sqlite:///",
        "system": "sqlite:///",
    }


class ProductionConfig(Config):
    SQLALCHEMY_DATABASE_URI = "mysql://user@localhost/foo"


config_dict = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}
