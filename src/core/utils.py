from __future__ import annotations

import asyncio
import base64
import dataclasses
from datetime import date, datetime, time, timezone
from functools import wraps
import json as _json
import logging
import logging.config
import os
import platform
import socket
import typing as t
import uuid

import cachetools
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import geopy
import jwt
from sqlalchemy.engine import Row

from config import Config
from src.core.g import base_dir


coordinates = cachetools.LFUCache(maxsize=16)


def async_to_sync(func: t.Callable):
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
    secret_key = Config.SECRET_KEY

    @staticmethod
    def dumps(payload: dict, secret_key: t.Optional[str] = None) -> str:
        secret_key = secret_key or Tokenizer.secret_key
        return jwt.encode(payload, secret_key, algorithm=Tokenizer.algorithm)

    @staticmethod
    def loads(token: str, secret_key: t.Optional[str] = None) -> dict:
        secret_key = secret_key or Tokenizer.secret_key
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


def time_to_datetime(_time: t.Optional[time]) -> t.Optional[datetime]:
    # return _time in case it is None
    if not isinstance(_time, time):
        return _time
    return datetime.combine(date.today(), _time, tzinfo=timezone.utc)


def parse_sun_times(moment: str | datetime) -> datetime:
    if isinstance(moment, datetime):
        return moment
    _time = datetime.strptime(moment, "%I:%M:%S %p").time()
    return datetime.combine(date.today(), _time, tzinfo=timezone.utc)


def try_iso_format(time_obj: time) -> t.Optional[str]:
    try:
        return time_to_datetime(time_obj).isoformat()
    except TypeError:  # time_obj is None or Null
        return None


def config_dict_from_class(obj: type) -> dict:
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


def configure_logging(config_class) -> None:
    DEBUG = config_class.DEBUG
    LOG_TO_STDOUT = config_class.LOG_TO_STDOUT
    LOG_TO_FILE = config_class.LOG_TO_FILE
    LOG_ERROR = config_class.LOG_ERROR

    handlers = []

    if LOG_TO_STDOUT:
        handlers.append("streamHandler")

    if any((LOG_TO_FILE, LOG_ERROR)):
        logs_dir = base_dir / "logs"
        if not logs_dir.exists():
            logs_dir.mkdir()

    if LOG_TO_FILE & 0:
        handlers.append("fileHandler")

    if LOG_ERROR & 0:
        handlers.append("errorFileHandler")

    LOGGING_CONFIG = {
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
                "level": f"{'DEBUG' if DEBUG else 'INFO'}",
                "formatter": "streamFormat",
                "class": "logging.StreamHandler",
            },
            "fileHandler": {
                "level": f"{'DEBUG' if DEBUG else 'INFO'}",
                "formatter": "fileFormat",
                "class": "logging.handlers.RotatingFileHandler",
                "filename": "logs/base.log",
                "mode": "a",
                "maxBytes": 1024 * 512,
                "backupCount": 5,
            },
            "errorFileHandler": {
                "level": "ERROR",
                "formatter": "fileFormat",
                "class": "logging.FileHandler",
                "filename": "logs/errors.log",
                "mode": "a",
            }
        },
        "loggers": {
            "": {
                "handlers": handlers,
                "level": f"{'DEBUG' if DEBUG else 'INFO'}"
            },
            "aiosqlite": {
                "handlers": handlers,
                "level": "WARNING",
                "propagate": False,
            },
            "apscheduler": {
                "handlers": handlers,
                "level": f"{'DEBUG' if DEBUG else 'WARNING'}",
                "propagate": False,
            },
            "urllib3": {
                "handlers": handlers,
                "level": "WARNING",
                "propagate": False,
            },
            "engineio": {
                "handlers": handlers,
                "level": f"{'DEBUG' if DEBUG else 'WARNING'}",
                #"propagate": False,
            },
            "socketio": {
                "handlers": handlers,
                "level": f"{'DEBUG' if DEBUG else 'WARNING'}",
                #"propagate": False,

            },
            "uvicorn": {
                "handlers": handlers,
                "level": f"{'DEBUG' if DEBUG else 'WARNING'}",
                # "propagate": False,
            },
        },
    }
    logging.config.dictConfig(LOGGING_CONFIG)


def decrypt_uid(encrypted_uid: str) -> str:
    h = hashes.Hash(hashes.SHA256())
    # TODO: use a better structure
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