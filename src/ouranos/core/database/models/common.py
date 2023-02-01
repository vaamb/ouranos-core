from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.ext.declarative import declared_attr
from sqlalchemy.schema import UniqueConstraint

from ouranos import db


base = db.Model


# ---------------------------------------------------------------------------
#   Base models common.py to main app and archive
# ---------------------------------------------------------------------------
class BaseSensorHistory(base):
    __abstract__ = True

    id: Mapped[int] = mapped_column(nullable=False, primary_key=True)
    measure: Mapped[int] = mapped_column(nullable=False)
    timestamp: Mapped[datetime] = mapped_column(nullable=False)
    value: Mapped[float] = mapped_column(sa.Float(precision=2), nullable=False)

    @declared_attr
    def ecosystem_uid(cls) -> Mapped[str]:
        return mapped_column(
            sa.String(length=8), sa.ForeignKey("ecosystems.uid"), nullable=False, index=True
        )

    @declared_attr
    def sensor_uid(cls) -> Mapped[str]:
        return mapped_column(
            sa.String(length=16), sa.ForeignKey("hardware.uid"), nullable=False, index=True
        )

    __table_args__ = (
        UniqueConstraint("measure", "timestamp", "value", "ecosystem_uid",
                         "sensor_uid", name="_no_repost_constraint"),
    )


class BaseActuatorHistory(base):
    __abstract__ = True

    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[str] = mapped_column(sa.String(length=16))
    timestamp: Mapped[datetime] = mapped_column(nullable=False)
    mode: Mapped[str] = mapped_column(sa.String(length=16))
    status: Mapped[bool] = mapped_column()

    @declared_attr
    def ecosystem_uid(cls) -> Mapped[str]:
        return mapped_column(
            sa.String(length=8), sa.ForeignKey("ecosystems.uid"), nullable=False, index=True
        )


class BaseHealth(base):
    __abstract__ = True

    id: Mapped[int] = mapped_column(primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(nullable=False)
    green: Mapped[int] = mapped_column()
    necrosis: Mapped[int] = mapped_column()
    health_index: Mapped[int] = mapped_column()

    @declared_attr
    def ecosystem_uid(cls) -> Mapped[str]:
        return mapped_column(
            sa.String(length=8), sa.ForeignKey("ecosystems.uid"), nullable=False, index=True
        )


class BaseWarning(base):
    __abstract__ = True

    id: Mapped[int] = mapped_column(primary_key=True)
    emergency: Mapped[int] = mapped_column()
    title: Mapped[str] = mapped_column(sa.String(length=256))
    description: Mapped[str] = mapped_column(sa.String(length=2048))
    created_on: Mapped[datetime] = mapped_column()
    seen_on: Mapped[datetime] = mapped_column()
    solved_on: Mapped[datetime] = mapped_column()

    def to_dict(self) -> dict:
        return {
            "emergency": self.emergency,
            "title": self.title,
            "description": self.description,
        }

    @property
    def seen(self):
        return self.seen_on is not None

    @property
    def solved(self):
        return self.solved_on is not None
