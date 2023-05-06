import os


DIR = os.environ.get("OURANOS_DIR") or os.getcwd()


class BaseConfig:
    DEBUG = False
    DEVELOPMENT = False
    TESTING = False

    LOG_DIR = os.environ.get("OURANOS_LOG_DIR") or os.path.join(DIR, "logs")
    CACHE_DIR = os.environ.get("OURANOS_CACHE_DIR") or os.path.join(DIR, ".cache")
    DB_DIR = os.environ.get("OURANOS_CACHE_DIR") or os.path.join(DIR, "DBs")

    SECRET_KEY = os.environ.get("OURANOS_SECRET_KEY") or "secret_key"
    CONNECTION_KEY = os.environ.get("OURANOS_CONNECTION_KEY") or SECRET_KEY

    # Logging config
    LOG_TO_STDOUT = True
    LOG_TO_FILE = True
    LOG_ERROR = True

    # Brokers config
    GAIA_COMMUNICATION_URL = os.environ.get("GAIA_COMMUNICATION_URL") or "amqp://"  # amqp:// or socketio://
    DISPATCHER_URL = os.environ.get("OURANOS_DISPATCHER_URL") or "memory://"  # or memory:// or amqp://
    SIO_MANAGER_URL = os.environ.get("OURANOS_SIO_MANAGER_URL") or "memory://"  # memory:// or amqp:// or redis://
    CACHE_SERVER_URL = os.environ.get("OURANOS_CACHE_URL") or "memory://"  # or memory:// or redis://

    # Services
    START_API = os.environ.get("OURANOS_START_API", True)
    API_HOST = os.environ.get("OURANOS_API_HOST", "127.0.0.1")
    API_PORT = os.environ.get("OURANOS_API_PORT", 5000)
    API_WORKERS = os.environ.get("OURANOS_API_WORKERS", 1)
    SERVER_RELOAD = False
    START_AGGREGATOR = os.environ.get("OURANOS_START_AGGREGATOR", True)
    AGGREGATOR_PORT = os.environ.get("OURANOS_AGGREGATOR_PORT", API_PORT)
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
    SQLALCHEMY_DATABASE_URI = (
            os.environ.get("OURANOS_DATABASE_URI") or
            "sqlite+aiosqlite:///" + os.path.join(DB_DIR, "ecosystems.db")
    )
    SQLALCHEMY_BINDS = {
        "app": (os.environ.get("OURANOS_APP_DATABASE_URI") or
                "sqlite+aiosqlite:///" + os.path.join(DB_DIR, "app.db")),
        "system": (os.environ.get("OURANOS_SYSTEM_DATABASE_URI") or
                   "sqlite+aiosqlite:///" + os.path.join(DB_DIR, "system.db")),
        "archive": (os.environ.get("OURANOS_ARCHIVE_DATABASE_URI") or
                    "sqlite+aiosqlite:///" + os.path.join(DB_DIR, "archive.db")),
        "memory": "sqlite+aiosqlite:///" if CACHE_SERVER_URL == "memory://"
                  else CACHE_SERVER_URL,
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
