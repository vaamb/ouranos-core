import logging
import logging.config
import os

try:
    from private_config import privateConfig
except ImportError:
    class privateConfig:
        ADMIN = None
        HOME_CITY = "Somewhere over the rainbow"
        HOME_COORDINATES = (0.0, 0.0)
        DARKSKY_API_KEY = None
        TELEGRAM_BOT_TOKEN = None


base_dir = os.path.abspath(os.path.dirname(__file__))


class Config():
    APP_NAME = "gaiaWeb"

    # Flask config
    DEBUG = False
    TESTING = False
    SECRET_KEY = os.environ.get("SECRET_KEY") or "BXhNmCEmNdoBNngyGXj6jJtooYAcKpt6"

    # SQLAlchemy config
    SQLALCHEMY_DATABASE_URI = "sqlite:///" + os.path.join(base_dir, "db_ecosystems.db")
    SQLALCHEMY_BINDS = {
        "app": "sqlite:///" + os.path.join(base_dir, "db_app.db"),
        "archive": "sqlite:///" + os.path.join(base_dir, "db_archive.db")
    }
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_RECORD_QUERIES = True
    SLOW_DB_QUERY_TIME = 0.5

    # Mail config
    MAIL_SERVER = os.environ.get("MAIL_SERVER")
    MAIL_PORT = int(os.environ.get("MAIL_PORT") or 25)
    MAIL_USE_TLS = os.environ.get("MAIL_USE_TLS") is not None
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD")

    # GAIA config
    GAIA_ADMIN = os.environ.get("GAIA_ADMIN") or privateConfig.ADMIN
    TEST_CONNECTION_IP = "1.1.1.1"
    RECAP_SENDING_HOUR = 4
    ECOSYSTEM_TIMEOUT = 5  # Time after which the ecosystem is considered as not working

    # Data logging
    SYSTEM_LOGGING_FREQUENCY = 10
    SENSORS_LOGGING_FREQUENCY = 10
    
    # Private parameters
    HOME_CITY = os.environ.get("HOME_CITY") or privateConfig.HOME_CITY
    HOME_COORDINATES = os.environ.get("HOME_COORDINATES") or privateConfig.HOME_COORDINATES
    DARKSKY_API_KEY = os.environ.get("DARKSKY_API_KEY") or privateConfig.DARKSKY_API_KEY
    TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN") or privateConfig.TELEGRAM_BOT_TOKEN


class DevelopmentConfig(Config):
    DEBUG = True


class TestingConfig(Config):
    TESTING = True


class ProductionConfig(Config):
    DATABASE_URI = "mysql://user@localhost/foo"


def configure_logging():
    DEBUG = True
    LOG_TO_STDOUT = True
    handler = "streamHandler"
    if not LOG_TO_STDOUT:
        if not os.path.exists(base_dir/"logs"):
            os.mkdir(base_dir/"logs")
        handler = "fileHandler"

    LOGGING_CONFIG = {
        "version": 1,
        "disable_existing_loggers": False,

        "formatters": {
            "streamFormat": {
                "format": "%(asctime)s [%(levelname)-4.4s] %(name)-20.20s: %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S"
            },
            "fileFormat": {
                "format": "%(asctime)s -- %(levelname)s  -- %(name)s -- %(message)s",
            },
        },

        "handlers": {
            "streamHandler": {
                "level": f"{'DEBUG' if DEBUG else 'INFO'}",
                "formatter": "streamFormat",
                "class": "logging.StreamHandler",
            },
        },

        "loggers": {
            "": {
                "handlers": [handler],
                "level": f"{'DEBUG' if DEBUG else 'INFO'}"
            },
            "apscheduler": {
                "handlers": [handler],
                "level": "WARNING"
            },
            "urllib3": {
                "handlers": [handler],
                "level": "WARNING"
            },
            "engineio": {
                "handlers": [handler],
                "level": "WARNING"
            },
            "socketio": {
                "handlers": [handler],
                "level": "WARNING"
            },
        },
    }

    logging.config.dictConfig(LOGGING_CONFIG)


configure_logging()
