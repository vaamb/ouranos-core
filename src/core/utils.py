from __future__ import annotations

import asyncio
import base64
import dataclasses
from datetime import date, datetime, time, timezone
from functools import wraps
import logging
import logging.config
from pathlib import Path
import socket
import typing as t
from typing import Any
import uuid
import warnings

import cachetools
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import geopy
import jwt
from sqlalchemy.engine import Row

import default
from src.core.g import base_dir, config as global_config

try:
    import orjson
except ImportError:
    warnings.warn("Ouranos could be faster if orjson was installed")

    import json as _json

    def _serializer(self, o: Any) -> dict | str:
        if isinstance(o, datetime):
            return o.astimezone(tz=timezone.utc).isoformat(timespec="seconds")
        if isinstance(o, date):
            return o.isoformat()
        if isinstance(o, time):
            return (
                datetime.combine(date.today(), o).astimezone(tz=timezone.utc)
                .isoformat(timespec="seconds")
            )
        if isinstance(o, uuid.UUID):
            return str(o)
        if isinstance(o, Row):
            return o._mapping  # return a tuple
        #             return {**o._mapping}  # return a dict
        if dataclasses.is_dataclass(o):
            return dataclasses.asdict(o)
        if hasattr(o, "__html__"):
            return str(o.__html__())
        return _json.JSONEncoder.default(self, o)

    class json:
        @staticmethod
        def dumps(obj) -> bytes:
            return _json.dumps(obj, default=_serializer).encode("utf8")

        @staticmethod
        def loads(obj) -> t.Any:
            return _json.loads(obj)

else:
    def _serializer(self, o: Any) -> dict | str:
        if isinstance(o, Row):
            return o._data  # return a tuple
        #             return {**o._mapping}  # return a dict
        if hasattr(o, "__html__"):
            return str(o.__html__())
        return _json.JSONEncoder.default(self, o)

    class json:
        @staticmethod
        def dumps(obj) -> bytes:
            return orjson.dumps(obj, default=_serializer)

        @staticmethod
        def loads(obj) -> t.Any:
            return orjson.loads(obj)


coordinates = cachetools.LFUCache(maxsize=16)


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


def async_to_sync(func: t.Callable) -> t.Callable:
    """Decorator to allow calling an async function like a sync function"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        ret = asyncio.run(func(*args, **kwargs))
        return ret
    return wrapper


class ExpiredTokenError(Exception):
    pass


class InvalidTokenError(Exception):
    pass


class Tokenizer:
    algorithm = "HS256"
    secret_key: str | None = global_config.get("SECRET_KEY", None)

    @staticmethod
    def dumps(payload: dict, secret_key: str | None = None) -> str:
        secret_key = secret_key or Tokenizer.secret_key
        if not secret_key:
            raise RuntimeError(
                "Either provide a `secret_key` or setup `Tokenizer.secret_key`"
            )
        return jwt.encode(payload, secret_key, algorithm=Tokenizer.algorithm)

    @staticmethod
    def loads(token: str, secret_key: str | None = None) -> dict:
        secret_key = secret_key or Tokenizer.secret_key
        if not secret_key:
            raise RuntimeError(
                "Either provide a `secret_key` or setup `Tokenizer.secret_key`"
            )
        try:
            payload = jwt.decode(token, secret_key,
                                 algorithms=[Tokenizer.algorithm])
            return payload
        except jwt.ExpiredSignatureError:
            raise ExpiredTokenError
        except jwt.PyJWTError:
            raise InvalidTokenError


def create_dispatcher(name: str, config: dict | None = None, **kwargs):
    config = config or global_config
    if not config:
        raise RuntimeError(
            "Either provide a config dict or set config globally with "
            "g.set_app_config"
        )
    broker_url = config.get("DISPATCHER_URL", default.DISPATCHER_URL)
    if broker_url.startswith("memory://"):
        from dispatcher import AsyncBaseDispatcher
        return AsyncBaseDispatcher(name, **kwargs)
    elif broker_url.startswith("redis://"):
        from dispatcher import AsyncRedisDispatcher
        uri = broker_url.removeprefix("redis://")
        if not uri:
            uri = "localhost:6379/0"
        url = f"redis://{uri}"
        return AsyncRedisDispatcher(name, url, **kwargs)
    elif broker_url.startswith("amqp://"):
        from dispatcher import AsyncAMQPDispatcher
        uri = broker_url.removeprefix("amqp://")
        if not uri:
            uri = "guest:guest@localhost:5672//"
        url = f"amqp://{uri}"
        return AsyncAMQPDispatcher(name, url, **kwargs)
    else:
        raise RuntimeError(
            "'DISPATCHER_URL' is not set to a supported protocol, choose"
            "from 'memory', 'redis' or 'amqp'"
        )


def is_connected(ip_to_connect: str = "1.1.1.1") -> bool:
    try:
        host = socket.gethostbyname(ip_to_connect)
        s = socket.create_connection((host, 80), 2)
        s.close()
        return True
    except Exception as ex:
        print(ex)
    return False


def time_to_datetime(_time: time | None) -> datetime | None:
    # return _time in case it is None
    if not isinstance(_time, time):
        return _time
    return datetime.combine(date.today(), _time, tzinfo=timezone.utc)


def parse_sun_times(moment: str | datetime) -> datetime:
    if isinstance(moment, datetime):
        return moment
    _time = datetime.strptime(moment, "%I:%M:%S %p").time()
    return datetime.combine(date.today(), _time, tzinfo=timezone.utc)


def try_iso_format(time_obj: time) -> str | None:
    try:
        return time_to_datetime(time_obj).isoformat()
    except TypeError:  # time_obj is None or Null
        return None


def configure_logging(config: dict) -> None:
    debug = config.get("DEBUG")
    log_to_stdout = config.get("LOG_TO_STDOUT")
    log_to_file = config.get("LOG_TO_FILE")
    log_error = config.get("LOG_ERROR")

    handlers = []

    if log_to_stdout:
        handlers.append("streamHandler")

    logs_dir_path = config.get("LOG_DIR")
    if logs_dir_path:
        try:
            logs_dir = Path(logs_dir_path)
        except ValueError:
            print("Invalid logging path, logging in base dir")
            logs_dir = base_dir / ".logs"
    else:
        logs_dir = base_dir / ".logs"

    if any((log_to_file, log_error)):
        if not logs_dir.exists():
            logs_dir.mkdir()
        if log_to_file:
            handlers.append("fileHandler")
        if log_error:
            handlers.append("errorFileHandler")

    logging_config = {
        "version": 1,
        "disable_existing_loggers": True,

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
                "level": f"{'DEBUG' if debug else 'INFO'}",
                "formatter": "streamFormat",
                "class": "logging.StreamHandler",
            },
            "fileHandler": {
                "level": f"{'DEBUG' if debug else 'INFO'}",
                "formatter": "fileFormat",
                "class": "logging.handlers.RotatingFileHandler",
                "filename": f"{logs_dir/'base.log'}",
                "mode": "a",
                "maxBytes": 1024 * 512,
                "backupCount": 5,
            },
            "errorFileHandler": {
                "level": "ERROR",
                "formatter": "fileFormat",
                "class": "logging.FileHandler",
                "filename": f"{logs_dir/'errors.log'}",
                "mode": "a",
            }
        },
        "loggers": {
            "": {
                "handlers": handlers,
                "level": f"{'DEBUG' if debug else 'INFO'}"
            },
            "aiosqlite": {
                "handlers": handlers,
                "level": "WARNING",
                "propagate": False,
            },
            "apscheduler": {
                "handlers": handlers,
                "level": f"{'DEBUG' if debug else 'WARNING'}",
                "propagate": False,
            },
            "urllib3": {
                "handlers": handlers,
                "level": "WARNING",
                "propagate": False,
            },
            "engineio": {
                "handlers": handlers,
                "level": f"{'DEBUG' if debug else 'WARNING'}",
                #"propagate": False,
            },
            "socketio": {
                "handlers": handlers,
                "level": f"{'DEBUG' if debug else 'WARNING'}",
                #"propagate": False,

            },
            "uvicorn": {
                "handlers": handlers,
                "level": f"{'DEBUG' if debug else 'WARNING'}",
                # "propagate": False,
            },
        },
    }
    logging.config.dictConfig(logging_config)


def decrypt_uid(encrypted_uid: str, secret_key: str = None) -> str:
    secret_key = secret_key or global_config.get("OURANOS_CONNECTION_KEY", None)
    if not secret_key:
        raise RuntimeError(
            "Either provide a `secret_key` or setup `CONNECTION_KEY` in config "
            "file or `OURANOS_CONNECTION_KEY` in the environment"
        )
    h = hashes.Hash(hashes.SHA256())
    h.update(secret_key.encode("utf-8"))
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
    print(skey)
    return skey


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


def stripped_warning(msg):
    def custom_format_warning(_msg, *args, **kwargs):
        return str(_msg) + '\n'

    format_warning = warnings.formatwarning
    warnings.formatwarning = custom_format_warning
    warnings.warn(msg)
    warnings.formatwarning = format_warning
