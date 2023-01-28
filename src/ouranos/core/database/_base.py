from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.declarative import declarative_base, DeclarativeMeta


@dataclass(frozen=True)
class ArchiveLink:
    name: str
    status: str
    _limit_key: str | None

    def __init__(self, name, status, _limit_key=None):
        if status not in ("archive", "recent"):
            raise ValueError("status has to be 'archive' or 'recent'")
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "_limit_key", _limit_key)

    @property
    def limit(self) -> int | None:
        from ouranos import current_app
        if self._limit_key is not None:
            return current_app.get(self._limit_key, None)
        return None


class BindMetaMixin(type):
    # From Flask-SQLAlchemy
    def __init__(cls, name, bases, d):
        bind_key = (
            d.pop('__bind_key__', None)
            or getattr(cls, '__bind_key__', None)
        )

        super(BindMetaMixin, cls).__init__(name, bases, d)

        if bind_key is not None and getattr(cls, '__table__', None) is not None:
            cls.__table__.info['bind_key'] = bind_key


class ArchiveMetaMixin(type):
    def __init__(cls, name, bases, d):
        archive_link = (
            d.pop('__archive_link__', None)
            or getattr(cls, '__archive_link__', None)
        )

        super(ArchiveMetaMixin, cls).__init__(name, bases, d)

        if archive_link is not None and getattr(cls, '__table__', None) is not None:
            cls.__table__.info['archive_link'] = archive_link


class CustomMeta(ArchiveMetaMixin, BindMetaMixin, DeclarativeMeta):
    pass


base: CustomMeta = declarative_base(metaclass=CustomMeta)