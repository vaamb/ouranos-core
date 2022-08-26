import asyncio
import dataclasses
from datetime import date, datetime, time, timezone
from functools import wraps
import logging
import logging.config
import os
from pathlib import Path
import socket
import typing as t
import uuid

import json as _json
import jwt
from sqlalchemy.engine import Row

#TODO: use local context?
from config import Config

base_dir = Path(__file__).absolute().parents[1]
logs_dir = base_dir/"logs"


def async_to_sync(func):
    """Decorator to allow calling an async function like a sync function"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        ret = asyncio.run(func(*args, **kwargs))
        return ret
    return wrapper


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
            return (
                datetime.combine(date.today(), o).replace(tzinfo=timezone.utc)
                        .isoformat(timespec="seconds")
            )
        if isinstance(o, uuid.UUID):
            return str(o)
        if isinstance(o, Row):
            return o._data  # return a tuple
#             return {**o._mapping}  # return a dict
        if dataclasses.is_dataclass(o):
            return dataclasses.asdict(o)
        if hasattr(o, "__html__"):
            return str(o.__html__())
        return _json.JSONEncoder.default(self, o)


class JSONDecoder(_json.JSONDecoder):
    def decode(self, string, *args, **kwargs):
        result = super(JSONDecoder, self).decode(string, *args, **kwargs)
        return self._convert_number(result)

    def _convert_number(self, o):
        if isinstance(o, str):
            try:
                return int(o)
            except ValueError:
                try:
                    return float(o)
                except ValueError:
                    return o
        elif isinstance(o, dict):
            # If needed, can convert key too
            return {k: self._convert_number(v) for k, v in o.items()}
        elif isinstance(o, list):
            return [self._convert_number(v) for v in o]
        else:
            return o


class json:
    @staticmethod
    def dumps(*args, **kwargs):
        if 'cls' not in kwargs:
            kwargs['cls'] = JSONEncoder
        return _json.dumps(*args, **kwargs)

    @staticmethod
    def loads(*args, **kwargs):
        if 'cls' not in kwargs:
            kwargs['cls'] = JSONDecoder
        return _json.loads(*args, **kwargs)


class ExpiredTokenError(Exception):
    pass


class InvalidTokenError(Exception):
    pass


class Tokenizer:
    algorithm = "HS256"

    @staticmethod
    def dumps(payload: dict, secret_key: t.Optional[str] = None) -> str:
        if not secret_key:
            secret_key = Config.SECRET_KEY
        return jwt.encode(payload, secret_key, algorithm=Tokenizer.algorithm)

    @staticmethod
    def loads(token: str, secret_key: t.Optional[str] = None) -> dict:
        if not secret_key:
            secret_key = Config.SECRET_KEY
        try:
            payload = jwt.decode(token, secret_key,
                                 algorithms=[Tokenizer.algorithm])
            return payload
        except jwt.ExpiredSignatureError:
            raise ExpiredTokenError
        except jwt.PyJWTError:
            raise InvalidTokenError


def is_connected(ip_to_connect: str = "1.1.1.1") -> bool:
    try:
        host = socket.gethostbyname(ip_to_connect)
        s = socket.create_connection((host, 80), 2)
        s.close()
        return True
    except Exception as ex:
        print(ex)
    return False


def time_to_datetime(_time: time):
    # return _time in case it is None
    if not isinstance(_time, time):
        return _time
    return datetime.combine(date.today(), _time, tzinfo=timezone.utc)


def parse_sun_times(moment: str) -> datetime:
    _time = datetime.strptime(moment, "%I:%M:%S %p").time()
    return datetime.combine(date.today(), _time,
                            tzinfo=timezone.utc)


def try_iso_format(time_obj):
    try:
        return time_to_datetime(time_obj).isoformat()
    except TypeError:  # time_obj is None or Null
        return None


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
    LOG_TO_STDOUT = config_class.LOG_TO_STDOUT
    LOG_TO_FILE = config_class.LOG_TO_FILE
    LOG_ERROR = config_class.LOG_ERROR

    handlers = []

    if LOG_TO_STDOUT:
        handlers.append("streamHandler")

    if any((LOG_TO_FILE, LOG_ERROR)):
        if not os.path.exists(logs_dir):
            os.mkdir(logs_dir)

    if LOG_TO_FILE & 0:
        handlers.append("fileHandler")

    if LOG_ERROR & 0:
        handlers.append("errorFileHandler")

    LOGGING_CONFIG = {
        "version": 1,
        "disable_existing_loggers": False,

        "formatters": {
            "streamFormat": {
                "format": "%(asctime)s %(levelname)-4.4s [%(filename)-20.20s:%(lineno)3d] %(name)-35.35s: %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S"
            },
            "fileFormat": {
                "format": "%(asctime)s -- %(levelname)s  -- %(name)s -- %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S"
            },
        },
        "handlers": {
            "streamHandler": {
                "level": f"{'DEBUG' if DEBUG else 'INFO'}",
                "formatter": "streamFormat",
                "class": "logging.StreamHandler",
            },
#            "fileHandler": {
#                "level": f"{'DEBUG' if DEBUG else 'INFO'}",
#                "formatter": "fileFormat",
#                "class": "logging.handlers.RotatingFileHandler",
#                'filename': 'logs/base.log',
#                'mode': 'w+',
#                'maxBytes': 1024 * 512,
#                'backupCount': 5,
#            },
#            "errorFileHandler": {
#                "level": "ERROR",
#                "formatter": "fileFormat",
#                "class": "logging.FileHandler",
#                'filename': 'logs/errors.log',
#                'mode': 'a',
#            }
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
    logging.config.dictConfig(LOGGING_CONFIG)
