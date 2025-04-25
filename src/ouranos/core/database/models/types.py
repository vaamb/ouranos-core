from datetime import datetime, timezone
from enum import IntEnum
from pathlib import Path

from anyio import Path as ioPath
from sqlalchemy.types import DateTime, Integer, String, TypeDecorator


class UtcDateTime(TypeDecorator):
    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if isinstance(value, datetime):
            return value.astimezone(timezone.utc)
        return value

    def process_result_value(self, value, dialect):
        if isinstance(value, datetime):
            return value.replace(tzinfo=timezone.utc)
        return value


class PathType(TypeDecorator):
    impl = String
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if isinstance(value, (ioPath, Path)):
            return str(value)
        return value

    def process_result_value(self, value, dialect):
        if value is not None:
            return ioPath(value)
        return value


class SQLIntEnum(TypeDecorator):
    impl = Integer
    cache_ok = True

    def __init__(self, enum_type, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._enum_type = enum_type

    def process_bind_param(self, value, dialect):
        if isinstance(value, IntEnum):
            return value.value
        return value

    def process_result_value(self, value, dialect):
        return self._enum_type(value)
