from collections import OrderedDict
import logging
import logging.config
import os
from pathlib import Path
import socket

import geopy

from config import Config


cache_dir = Path(__file__).absolute().parents[1]/"cache"
if not cache_dir:
    os.mkdir(cache_dir)


class LRU(OrderedDict):
    # Recipe taken from python doc
    def __init__(self, maxsize=32, *args, **kwargs):
        self.maxsize = maxsize
        super().__init__(*args, **kwargs)

    def __getitem__(self, key):
        value = super().__getitem__(key)
        self.move_to_end(key)
        return value

    def __setitem__(self, key, value):
        if key in self:
            self.move_to_end(key)
        super().__setitem__(key, value)
        if len(self) > self.maxsize:
            oldest = next(iter(self))
            del self[oldest]


coordinates = LRU(maxsize=16)


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
