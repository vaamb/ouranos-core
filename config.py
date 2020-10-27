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


class Config(privateConfig):
    APP_NAME = "gaiaWeb"
    # Flask config
    DEBUG = False
    TESTING = False
    SECRET_KEY = os.environ.get("SECRET_KEY") or "BXhNmCEmNdoBNngyGXj6jJtooYAcKpt6"

    # SQLAlchemy config
    SQLALCHEMY_DATABASE_URI = "sqlite:///" + os.path.join(base_dir, "app.db")
    # os.environ.get("DATABASE_URL") or \

    # SQLALCHEMY_DATABASE_URI = "mysql://Sensors:Adansonia7!@localhost/Gaia"
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
    TEST_CONNECTION_IP = "one.one.one.one"
    RECAP_SENDING_HOUR = 4

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
    DEBUG = False
    LOG_TO_STDOUT = True
    handler = "streamHandler"
    if not LOG_TO_STDOUT:
        if not os.path.exists("logs"):
            os.mkdir("logs")
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
            "fileHandler": {
                "level": f"{'DEBUG' if DEBUG else 'INFO'}",
                "formatter": "fileFormat",
                "class": "logging.handlers.RotatingFileHandler",
                "filename": "logs/gaia.log",
                "mode": "w",
                "maxBytes": 1024 * 32,
                "backupCount": 5,
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
