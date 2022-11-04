import sqlalchemy as sa
from sqlalchemy.ext.declarative import declared_attr
from sqlalchemy.schema import UniqueConstraint

from ouranos.core.g import db


base = db.Model


# ---------------------------------------------------------------------------
#   Base models common.py to main app and archive
# ---------------------------------------------------------------------------
class BaseSensorHistory(base):
    __abstract__ = True
    id = sa.Column(sa.Integer, autoincrement=True, nullable=False, primary_key=True)
    measure = sa.Column(sa.Integer, nullable=False)
    datetime = sa.Column(sa.DateTime, nullable=False)
    value = sa.Column(sa.Float(precision=2), nullable=False)

    @declared_attr
    def ecosystem_uid(cls):
        return sa.Column(sa.String(length=8), sa.ForeignKey("ecosystems.uid"),
                         nullable=False)

    @declared_attr
    def sensor_uid(cls):
        return sa.Column(sa.String(length=16), sa.ForeignKey("hardware.uid"),
                         nullable=False)

    __table_args__ = (
        UniqueConstraint("measure", "datetime", "value", "ecosystem_uid",
                         "sensor_uid", name="_no_repost_constraint"),
    )


class BaseActuatorHistory(base):
    __abstract__ = True
    id = sa.Column(sa.Integer, primary_key=True)
    type = sa.Column(sa.String(length=16))
    datetime = sa.Column(sa.DateTime, nullable=False)
    mode = sa.Column(sa.String(length=16))
    status = sa.Column(sa.Boolean)

    @declared_attr
    def ecosystem_uid(cls):
        return sa.Column(sa.String(length=8), sa.ForeignKey("ecosystems.uid"),
                         index=True)


class BaseHealth(base):
    __abstract__ = True
    id = sa.Column(sa.Integer, primary_key=True)
    datetime = sa.Column(sa.DateTime, nullable=False)
    green = sa.Column(sa.Integer)
    necrosis = sa.Column(sa.Integer)
    health_index = sa.Column(sa.Float(precision=1))

    @declared_attr
    def ecosystem_uid(cls):
        return sa.Column(sa.String(length=8), sa.ForeignKey("ecosystems.uid"),
                         index=True)


class BaseWarning(base):
    __abstract__ = True
    id = sa.Column(sa.Integer, primary_key=True)
    emergency = sa.Column(sa.Integer)
    title = sa.Column(sa.String(length=256))
    description = sa.Column(sa.String(length=2048))
    content = sa.Column(sa.String)
    created = sa.Column(sa.DateTime)
    seen = sa.Column(sa.DateTime)
    is_solved = sa.Column(sa.Boolean)
    solved = sa.Column(sa.DateTime)

    def to_dict(self) -> dict:
        return {
            "emergency": self.emergency,
            "title": self.title,
            "description": self.description,
            "content": self.content,
        }

    def content_only(self) -> str:
        return self.content
