from typing import Any

from sqlalchemy.orm import DeclarativeMeta
from sqlalchemy.sql.schema import MetaData

from sqlalchemy_wrapper.base import BindMetaMixin


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


naming_convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


custom_metadata = MetaData(naming_convention=naming_convention)
