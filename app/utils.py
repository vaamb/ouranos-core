import base64
from collections import OrderedDict
import logging
import logging.config
import os
from pathlib import Path
import socket

import cachetools
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import geopy

from config import Config


base_dir = Path(__file__).absolute().parents[1]


coordinates = cachetools.LFUCache(maxsize=16)


def get_coordinates(city: str) -> dict:
    """
    Memoize and return the geocode of the given city using geopy API. The
    memoization step allows to reduce the number of call to the Nominatim API.

    :param city: str, the name of a city.
    :return: dict with the latitude and longitude of the given city.
    """
    # if not memoized, look for coordinates
    if city not in coordinates:
        geolocator = geopy.geocoders.Nominatim(user_agent="EP-gaia")
        location = geolocator.geocode(city)
        coordinates[city] = {
            "latitude": location.latitude,
            "longitude": location.longitude
        }

    return coordinates[city]


def is_connected() -> bool:
    try:
        host = socket.gethostbyname(Config.TEST_CONNECTION_IP)
        s = socket.create_connection((host, 80), 2)
        s.close()
        return True
    except Exception as ex:
        print(ex)
    return False


def configure_logging(config_class):
    DEBUG = config_class.DEBUG
    TESTING = config_class.TESTING
    LOG_TO_STDOUT = config_class.LOG_TO_STDOUT
    LOG_TO_FILE = config_class.LOG_TO_FILE
    LOG_ERROR = config_class.LOG_ERROR

    handlers = []

    if LOG_TO_STDOUT:
        handlers.append("streamHandler")

    if LOG_TO_FILE or LOG_ERROR:
        if not os.path.exists(base_dir/"logs"):
            os.mkdir(base_dir/"logs")

    if LOG_TO_FILE:
        handlers.append("fileHandler")

    if LOG_ERROR:
        handlers.append("errorFileHandler")

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
                "datefmt": "%Y-%m-%d %H:%M:%S"
            },
            "errorFormat": {
                'format': '%(asctime)s %(levelname)-4.4s %(module)-17s ' +
                          'line:%(lineno)-4d  %(message)s',
                "datefmt": "%Y-%m-%d %H:%M:%S"
            },
        },

        "handlers": {
            "streamHandler": {
                "level": f"{'DEBUG' if DEBUG or TESTING else 'INFO'}",
                "formatter": "streamFormat",
                "class": "logging.StreamHandler",
            },
        },

        "loggers": {
            "": {
                "handlers": handlers,
                "level": f"{'DEBUG' if DEBUG or TESTING else 'INFO'}"
            },
            "apscheduler": {
                "handlers": handlers,
                "level": "WARNING"
            },
            "urllib3": {
                "handlers": handlers,
                "level": "WARNING"
            },
            "engineio": {
                "handlers": handlers,
                "level": "WARNING"
            },
            "socketio": {
                "handlers": handlers,
                "level": "WARNING"
            },
        },
    }

    # Append file handlers to config as if they are needed they require logs file
    if LOG_TO_FILE:
        LOGGING_CONFIG["handlers"].update({
            "fileHandler": {
                "level": f"{'DEBUG' if DEBUG or TESTING else 'INFO'}",
                "formatter": "fileFormat",
                "class": "logging.handlers.RotatingFileHandler",
                'filename': 'logs/gaiaWeb.log',
                'mode': 'w+',
                'maxBytes': 1024 * 512,
                'backupCount': 5,
            }
        })

    if LOG_ERROR:
        LOGGING_CONFIG["handlers"].update({
            "errorFileHandler": {
                "level": f"ERROR",
                "formatter": "errorFormat",
                "class": "logging.FileHandler",
                'filename': 'logs/gaiaWeb_errors.log',
                'mode': 'a',
            }
        })

    logging.config.dictConfig(LOGGING_CONFIG)


def decrypt_uid(encrypted_uid: str) -> str:
    h = hashes.Hash(hashes.SHA256())
    h.update(Config.GAIA_SECRET_KEY.encode("utf-8"))
    key = base64.urlsafe_b64encode(h.finalize())
    f = Fernet(key=key)
    try:
        return f.decrypt(encrypted_uid.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        return ""


def validate_uid_token(token: str, manager_uid: str) -> bool:
    iterations = int(token.split("$")[0].split(":")[2])
    ssalt = token.split("$")[1]
    token_key = token.split("$")[2]
    bsalt = ssalt.encode("UTF-8")

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=bsalt,
        iterations=iterations,
    )
    bkey = kdf.derive(manager_uid.encode())
    hkey = base64.b64encode(bkey).hex()
    return token_key == hkey


def generate_secret_key_from_password(password: str, set_env: bool = False) -> str:
    if isinstance(password, str):
        password = password.encode("utf-8")
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"",
        iterations=2**21,
    )
    bkey = kdf.derive(password)
    skey = base64.b64encode(bkey).decode("utf-8").strip("=")
    if set_env:
        if platform.system() in ("Linux", "Windows"):
            os.environ["GAIA_SECRET_KEY"] = skey
        else:
            # Setting environ in BSD and MacOsX can lead to mem leak (cf. doc)
            os.putenv("GAIA_SECRET_KEY", skey)
    return skey
