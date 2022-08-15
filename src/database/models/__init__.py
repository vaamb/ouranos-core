from dataclasses import dataclass

#from flask_sqlalchemy.model import DefaultMeta, Model
from sqlalchemy.ext.declarative import declarative_base


@dataclass(frozen=True)
class archive_link:
    name: str
    status: str

    def __init__(self, name, status):
        if status not in ("archive", "recent"):
            raise ValueError("status has to be 'archive' or 'recent'")
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "status", status)


class ArchiveMetaMixin(type):
    def __init__(cls, name, bases, d):
        archive_link = (
            d.pop('__archive_link__', None)
            or getattr(cls, '__archive_link__', None)
        )

        super(ArchiveMetaMixin, cls).__init__(name, bases, d)

        if archive_link is not None and getattr(cls, '__table__', None) is not None:
            cls.__table__.info['archive_link'] = archive_link


"""class CustomMeta(ArchiveMetaMixin, DefaultMeta):
    pass"""


base = declarative_base()
