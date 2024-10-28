from datetime import datetime, timezone
from pathlib import Path

from anyio import Path as ioPath
from sqlalchemy.types import DateTime, String, TypeDecorator


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
