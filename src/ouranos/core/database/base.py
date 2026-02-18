from sqlalchemy.orm import DeclarativeMeta
from sqlalchemy.sql.schema import MetaData

from sqlalchemy_wrapper.base import BindMetaMixin


class CustomMeta(BindMetaMixin, DeclarativeMeta):
    pass


naming_convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


custom_metadata = MetaData(naming_convention=naming_convention)
