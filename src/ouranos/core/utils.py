from __future__ import annotations

import asyncio
import base64
import dataclasses
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
import json as _json
import typing as t
from typing import Any
import uuid
import warnings

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from dispatcher import (
    AsyncDispatcher, AsyncInMemoryDispatcher, AsyncRedisDispatcher,
    AsyncAMQPDispatcher)
import jwt
from sqlalchemy import Row

from ouranos.core.exceptions import (
    ExpiredTokenError, InvalidTokenError, TokenError)

try:
    import orjson
except ImportError:
    warnings.warn("Ouranos could be faster if orjson was installed")

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
            return o.tuple()  # return a tuple
        #    return {**o._mapping}  # return a dict
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
            return o.tuple()  # return a tuple
        #    return {**o._mapping}  # return a dict
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


def setup_loop():
    try:
        import uvloop
        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    except ImportError:
        pass


@dataclass(frozen=True)
class timeWindow:
    start: datetime
    end: datetime

    def __repr__(self) -> str:
        return (
            f"<timeWindow(start={self.start.isoformat(timespec='minutes')}, "
            f"end={self.end.isoformat(timespec='minutes')})>"
        )


def create_time_window(
        start_time: str | datetime | None = None,
        end_time: str | datetime | None = None,
        window_length: int = 7,
        rounding_base: int = 10,
        grace_time: int = 60
) -> timeWindow:
    def extract_dt(dt: str | datetime, limit_name: str) -> datetime:
        if isinstance(dt, str):
            return datetime.fromisoformat(dt)
        elif isinstance(dt, datetime):
            return dt
        else:
            raise ValueError(f"'{limit_name}' is not a valid ISO (8601) time.")
    if end_time:
        end = extract_dt(end_time, "end_time")
    else:
        end = datetime.now(timezone.utc)
    if start_time:
        start = extract_dt(start_time, "start_time")
        if end - start > timedelta(days=window_length):
            raise ValueError(f"Max time window length is {window_length} days.")
    else:
        start = end - timedelta(days=window_length)
    if start > end:
        start, end = end, start
    return timeWindow(
        start=round_datetime(start, rounding_base, grace_time),
        end=round_datetime(end, rounding_base, grace_time),
    )


def round_datetime(
        dt: datetime,
        rounding_base: int = 10,
        grace_time: int = 60
) -> datetime:
    """ Round `dt` to the nearest `rounding_base` minutes to ease result caching
    """
    grace_time = timedelta(seconds=grace_time)
    rounded_minute = dt.minute // rounding_base * rounding_base
    return (
        dt.replace(minute=rounded_minute, second=0, microsecond=0) + grace_time
    )


def humanize_list(lst: list) -> str:
    list_length = len(lst)
    if list_length == 0:
        return ""
    elif list_length == 1:
        return lst[0]
    else:
        return f"{', '.join(lst[:list_length-1])} and {lst[list_length-1]}"


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
        except jwt.InvalidTokenError:
            raise InvalidTokenError
        except jwt.PyJWTError:
            raise TokenError

    @staticmethod
    def create_token(
            subject: str,
            expiration_delay: int = 60 * 60 * 24,
            other_claims: dict | None = None,
    ) -> str:
        payload = {
            "sub": subject,
            "exp": datetime.now(timezone.utc) + timedelta(seconds=expiration_delay),
        }
        other_claims = other_claims or {}
        for key, value in other_claims.items():
            if value is not None:
                payload[key] = value
        return Tokenizer.dumps(payload)


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


def stripped_warning(msg):
    def custom_format_warning(_msg, *args, **kwargs):
        return str(_msg) + '\n'

    format_warning = warnings.formatwarning
    warnings.formatwarning = custom_format_warning
    warnings.warn(msg)
    warnings.formatwarning = format_warning


def check_secret_key(config: dict) -> str | None:
    if any((config["DEVELOPMENT"], config["TESTING"])):
        return (
            "You are currently running Ouranos in development and/or testing mode"
        )
    else:
        for secret in ("SECRET_KEY", "CONNECTION_KEY"):
            if config.get(secret) == "secret_key":
                raise RuntimeError(
                    f"You need to set the environment variable '{secret}' when "
                    f"using Ouranos in a production environment."
                )
