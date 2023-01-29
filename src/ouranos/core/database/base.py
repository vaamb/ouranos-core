from __future__ import annotations

from typing import Any

from sqlalchemy.orm import declarative_base, DeclarativeMeta


class BindMetaMixin(type):
    # From Flask-SQLAlchemy
    def __init__(cls, classname: Any, bases: Any, dict_: Any) -> None:
        bind_key = (
            dict_.pop('__bind_key__', None)
            or getattr(cls, '__bind_key__', None)
        )

        super(BindMetaMixin, cls).__init__(classname, bases, dict_)

        if bind_key is not None and getattr(cls, '__table__', None) is not None:
            cls.__table__.info['bind_key'] = bind_key


class ArchiveMetaMixin(type):
    def __init__(cls, classname: Any, bases: Any, dict_: Any) -> None:
        archive_link = (
            dict_.pop('__archive_link__', None)
            or getattr(cls, '__archive_link__', None)
        )

        super(ArchiveMetaMixin, cls).__init__(classname, bases, dict_)

        if (
                archive_link is not None and
                getattr(cls, '__table__', None) is not None
        ):
            cls.__table__.info['archive_link'] = archive_link


class CustomMeta(ArchiveMetaMixin, BindMetaMixin, DeclarativeMeta):
    pass


base: CustomMeta = declarative_base(metaclass=CustomMeta)
