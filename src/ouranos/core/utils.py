from __future__ import annotations

import asyncio
import base64
import dataclasses
from datetime import date, datetime, time, timezone
from functools import wraps
import socket
import typing as t
from typing import Any
import uuid
import warnings

import cachetools
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from dispatcher import (
    AsyncBaseDispatcher, AsyncRedisDispatcher, AsyncAMQPDispatcher
)
import geopy
import jwt
from sqlalchemy.engine import Row

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


dispatcher_type: "AsyncBaseDispatcher" | "AsyncRedisDispatcher" | "AsyncAMQPDispatcher"

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

    @staticmethod
    def dumps(payload: dict, secret_key: str | None = None) -> str:
        from ouranos import current_app
        secret_key = secret_key or current_app.config["SECRET_KEY"]
        if not secret_key:
            raise RuntimeError(
                "Either provide a `secret_key` or setup `Tokenizer.secret_key`"
            )
        elif (
            not any((current_app.config["DEVELOPMENT"], current_app.config["TESTING"]))
            and secret_key == "secret_key"
        ):
            raise RuntimeError(
                "You need to set the environment variable 'SECRET_KEY' when "
                "using Ouranos in a production environment."
            )
        return jwt.encode(payload, secret_key, algorithm=Tokenizer.algorithm)

    @staticmethod
    def loads(token: str, secret_key: str | None = None) -> dict:
        from ouranos import current_app
        secret_key = secret_key or current_app.config["SECRET_KEY"]
        if not secret_key:
            raise RuntimeError(
                "Either provide a `secret_key` or setup `Tokenizer.secret_key`"
            )
        elif (
            not any((current_app.config["DEVELOPMENT"], current_app.config["TESTING"]))
            and secret_key == "secret_key"
        ):
            raise RuntimeError(
                "You need to set the environment variable 'SECRET_KEY' when "
                "using Ouranos in a production environment."
            )
        try:
            payload = jwt.decode(token, secret_key,
                                 algorithms=[Tokenizer.algorithm])
            return payload
        except jwt.ExpiredSignatureError:
            raise ExpiredTokenError
        except jwt.PyJWTError:
            raise InvalidTokenError


class DispatcherFactory:
    __dispatchers: dict[str, dispatcher_type] = {}

    @classmethod
    def get(
            cls,
            name: str,
            config: dict | None = None,
            **kwargs
    ) -> dispatcher_type:
        try:
            return cls.__dispatchers[name]
        except KeyError:
            from ouranos import current_app
            config = config or current_app.config
            broker_url = config["DISPATCHER_URL"]
            if broker_url.startswith("memory://"):
                return AsyncBaseDispatcher(name, **kwargs)
            elif broker_url.startswith("redis://"):
                uri = broker_url.removeprefix("redis://")
                if not uri:
                    uri = "localhost:6379/0"
                url = f"redis://{uri}"
                return AsyncRedisDispatcher(name, url, **kwargs)
            elif broker_url.startswith("amqp://"):
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


def time_to_datetime(_time: time | None) -> datetime | None:
    # return _time in case it is None
    if not isinstance(_time, time):
        return _time
    return datetime.combine(date.today(), _time, tzinfo=timezone.utc)


def try_iso_format(time_obj: time | None) -> str | None:
    if time_obj is not None:
        return time_to_datetime(time_obj).isoformat()
    return None


def decrypt_uid(encrypted_uid: str, secret_key: str = None) -> str:
    from ouranos import current_app
    secret_key = secret_key or current_app.config["OURANOS_CONNECTION_KEY"]
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


def generate_secret_key_from_password(password: str | bytes) -> str:
    if isinstance(password, str):
        pwd = password.encode("utf-8")
    else:
        pwd = password
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"",
        iterations=2**21,
    )
    bkey = kdf.derive(pwd)
    skey = base64.b64encode(bkey).decode("utf-8").strip("=")
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


def check_secret_key(config: dict) -> None:
    if any((config["DEVELOPMENT"], config["TESTING"])):
        stripped_warning(
            "You are currently running Ouranos in development and/or testing mode"
        )
    else:
        for secret in ("SECRET_KEY", "CONNECTION_KEY"):
            if config.get(secret) == "secret_key":
                raise RuntimeError(
                    f"You need to set the environment variable '{secret}' when "
                    f"using Ouranos in a production environment."
                )
