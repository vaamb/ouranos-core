from __future__ import annotations

from datetime import datetime, timezone
import enum
from typing import Optional

from gaia_validators import ActuatorMode
import sqlalchemy as sa
from sqlalchemy import UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.ext.declarative import declared_attr


from ouranos import db


_base = db.Model


class base(_base):
    __abstract__ = True

    def to_dict(self, exclude: list | None = None) -> dict:
        exclude: list = exclude or []
        return {
            key: value for key, value in vars(self).items()
            if key not in exclude
        }


class WarningLevel(enum.Enum):
    low = 0
    elevated = 1
    high = 2
    severe = 3
    critical = 4


# ---------------------------------------------------------------------------
#   Base models common.py to main app and archive
# ---------------------------------------------------------------------------
class BaseSensorHistory(base):
    __abstract__ = True

    id: Mapped[int] = mapped_column(primary_key=True)
    measure: Mapped[int] = mapped_column()
    timestamp: Mapped[datetime] = mapped_column()
    value: Mapped[float] = mapped_column(sa.Float(precision=2))

    @declared_attr
    def ecosystem_uid(cls) -> Mapped[str]:
        return mapped_column(
            sa.String(length=8), sa.ForeignKey("ecosystems.uid"), index=True
        )

    @declared_attr
    def sensor_uid(cls) -> Mapped[str]:
        return mapped_column(
            sa.String(length=16), sa.ForeignKey("hardware.uid"), index=True
        )

    __table_args__ = (
        UniqueConstraint("measure", "timestamp", "value", "ecosystem_uid",
                         "sensor_uid", name="_no_repost_constraint"),
    )


class BaseActuatorHistory(base):
    __abstract__ = True

    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[str] = mapped_column(sa.String(length=16))
    timestamp: Mapped[datetime] = mapped_column()
    mode: Mapped[ActuatorMode] = mapped_column(default=ActuatorMode.automatic)
    status: Mapped[bool] = mapped_column(default=False)

    @declared_attr
    def ecosystem_uid(cls) -> Mapped[str]:
        return mapped_column(
            sa.String(length=8), sa.ForeignKey("ecosystems.uid"), index=True
        )


class BaseHealth(base):
    __abstract__ = True

    id: Mapped[int] = mapped_column(primary_key=True)
    timestamp: Mapped[datetime] = mapped_column()
    green: Mapped[int] = mapped_column()
    necrosis: Mapped[int] = mapped_column()
    health_index: Mapped[int] = mapped_column()

    @declared_attr
    def ecosystem_uid(cls) -> Mapped[str]:
        return mapped_column(
            sa.String(length=8), sa.ForeignKey("ecosystems.uid"), index=True
        )


class BaseWarning(base):
    __abstract__ = True

    id: Mapped[int] = mapped_column(primary_key=True)
    level: Mapped[WarningLevel] = mapped_column(default=WarningLevel.low)
    title: Mapped[str] = mapped_column(sa.String(length=256))
    description: Mapped[Optional[str]] = mapped_column(sa.String(length=2048))
    created_on: Mapped[datetime] = mapped_column(default=datetime.now(timezone.utc))
    seen_on: Mapped[Optional[datetime]] = mapped_column()
    solved_on: Mapped[Optional[datetime]] = mapped_column()

    @property
    def seen(self):
        return self.seen_on is not None

    @property
    def solved(self):
        return self.solved_on is not None
