from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json as _json
import typing as t
from typing import Any
import warnings

import jwt
import orjson
from sqlalchemy import Row
from slugify import slugify as _slugify

from ouranos.core.exceptions import (
    ExpiredTokenError, InvalidTokenError, TokenError)


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
        window_length: int | None = 7,
        rounding_base: int = 10,
        grace_time: int = 60,
        max_window_length: int | None = 7,
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
        if max_window_length  and end - start > timedelta(days=max_window_length):
            raise ValueError(f"Max time window length is {max_window_length} days.")
    else:
        if window_length is None:
            raise ValueError(
                f"Cannot create a time window without a start time or a window "
                f"length."
            )
        start = end - timedelta(days=window_length)
    if start > end:
        start, end = end, start
    return timeWindow(
        start=round_datetime(start, rounding_base, 0),
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


def slugify(s: str) -> str:
    return _slugify(s, separator="_", lowercase=True)


def check_filename(full_filename: str, extensions: set[str]) -> None:
    split = full_filename.split(".")
    if len(split) != 2:
        if len(split) < 2:
            raise ValueError("The full filename with extension should be provided")
        raise ValueError("Files cannot contain '.' in their name")
    name, extension = split
    if extension.lower() not in extensions:
        raise ValueError(
            f"This file extension is not supported. Extensions supported: "
            f"{humanize_list([*extensions])}"
        )


def parse_str_value(value: str) -> int | float | bool | str:
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    return value
