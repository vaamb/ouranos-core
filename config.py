from pathlib import Path
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


base_dir = Path(__file__).absolute().parents[0]


class Config:
    APP_NAME = "gaiaWeb"

    # Flask config
    DEBUG = False
    TESTING = False
    # Use this key just to avoid a brute attack
    SECRET_KEY = os.environ.get("SECRET_KEY") or "BXhNmCEmNdoBNngyGXj6jJtooYAcKpt6"

    # Logging config
    LOG_TO_STDOUT = True
    LOG_TO_FILE = True
    # log error to file even if not log to file
    LOG_ERROR = True

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
    ECOSYSTEM_TIMEOUT = 150  # in sec
    WEATHER_UPDATE_PERIOD = 5  # in min
    GAIA_SECRET_KEY = os.environ.get("GAIA_SECRET_KEY") or \
                      "BXhNmCEmNdoBNngyGXj6jJtooYAcKpt6"
    GAIA_CLIENT_MAX_ATTEMPT = 3

    # Data logging
    SYSTEM_LOGGING_PERIOD = 10
    SENSORS_LOGGING_PERIOD = 10

    # Private parameters
    HOME_CITY = os.environ.get("HOME_CITY") or privateConfig.HOME_CITY
    HOME_COORDINATES = os.environ.get("HOME_COORDINATES") or privateConfig.HOME_COORDINATES
    DARKSKY_API_KEY = os.environ.get("DARKSKY_API_KEY") or privateConfig.DARKSKY_API_KEY
    TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN") or privateConfig.TELEGRAM_BOT_TOKEN


class DevelopmentConfig(Config):
    DEBUG = True
    LOG_TO_FILE = False


class TestingConfig(Config):
    TESTING = True


class ProductionConfig(Config):
    DATABASE_URI = "mysql://user@localhost/foo"
