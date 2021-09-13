import dataclasses
from datetime import date, datetime, time, timezone
import json as _json
import logging
import logging.config
import os
from pathlib import Path
import socket
import uuid

from flask.json import text_type
from flask import json as _json
from sqlalchemy.engine import Row


base_dir = Path(__file__).absolute().parents[1]
logs_dir = base_dir/"logs"


class JSONEncoder(_json.JSONEncoder):
    """ Rewriting of the default Flask JSON encoder to return iso date datetime
    and time as it is shorter and requires less transformations, resulting in
    slightly faster parsing whe formatting .

    In order to support more data types, override the :meth:`default`
    method.
    """
    def default(self, o):
        if isinstance(o, datetime):
            return o.replace(tzinfo=timezone.utc).isoformat(timespec="seconds")
        if isinstance(o, date):
            return o.isoformat()
        if isinstance(o, time):
            return o.isoformat(timespec="seconds")
        if isinstance(o, uuid.UUID):
            return str(o)
        if isinstance(o, Row):
            return o._data  # return a tuple
#             return {**o._mapping}  # return a dict
        if dataclasses and dataclasses.is_dataclass(o):
            return dataclasses.asdict(o)
        if hasattr(o, "__html__"):
            return text_type(o.__html__())
        return _json.JSONEncoder.default(self, o)


class json:
    @staticmethod
    def dumps(*args, **kwargs):
        if 'cls' not in kwargs:
            kwargs['cls'] = JSONEncoder
        return _json.dumps(*args, **kwargs)

    @staticmethod
    def loads(*args, **kwargs):
        return _json.loads(*args, **kwargs)


def is_connected(ip_to_connect: str = "1.1.1.1") -> bool:
    try:
        host = socket.gethostbyname(ip_to_connect)
        s = socket.create_connection((host, 80), 2)
        s.close()
        return True
    except Exception as ex:
        print(ex)
    return False


def time_to_datetime(_time: time) -> datetime:
    return datetime.combine(date.today(), _time, tzinfo=timezone.utc)


def parse_sun_times(moment: str) -> datetime:
    _time = datetime.strptime(moment, "%I:%M:%S %p").time()
    return datetime.combine(date.today(), _time,
                            tzinfo=timezone.utc)


def config_dict_from_class(obj) -> dict:
    config = {}
    for key in dir(obj):
        if key.isupper():
            config[key] = getattr(obj, key)
    return config


def humanize_list(lst: list) -> str:
    list_length = len(lst)
    sentence = []
    for i in range(list_length):
        sentence.append(lst[i])
        if i < list_length - 2:
            sentence.append(", ")
        elif i == list_length - 2:
            sentence.append(" and ")
    return "".join(sentence)


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
        if not os.path.exists(logs_dir):
            os.mkdir(logs_dir)

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
                "level": f"{'DEBUG' if DEBUG else 'INFO'}",
                "formatter": "streamFormat",
                "class": "logging.StreamHandler",
            },
        },

        "loggers": {
            "": {
                "handlers": handlers,
                "level": f"{'DEBUG' if DEBUG else 'INFO'}"
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
                "level": "INFO"
            },
            "socketio": {
                "handlers": handlers,
                "level": "INFO"
            },
        },
    }

    # TODO: move to main handlers?
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
