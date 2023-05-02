from datetime import datetime, timezone

from sqlalchemy.types import DateTime, TypeDecorator


class UtcDateTime(TypeDecorator):
    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if isinstance(value, datetime):
            return value.astimezone(timezone.utc)

    def process_result_value(self, value, dialect):
        if isinstance(value, datetime):
            return value.astimezone(timezone.utc)
