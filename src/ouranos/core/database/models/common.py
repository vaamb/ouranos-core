from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Self, Sequence

import sqlalchemy as sa
from sqlalchemy import insert, select, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.declarative import declared_attr

from gaia_validators import ActuatorMode

from ouranos import db
from ouranos.core.database.models.types import UtcDateTime


class WarningLevel(Enum):
    low = 0
    elevated = 1
    high = 2
    severe = 3
    critical = 4


class Base(db.Model):
    __abstract__ = True

    def to_dict(self, exclude: list | None = None) -> dict:
        exclude: list = exclude or []
        return {
            key: value for key, value in vars(self).items()
            if key not in exclude
        }


class Record:
    @classmethod
    async def create_records(
            cls,
            session: AsyncSession,
            values: dict | list[dict],
    ) -> None:
        stmt = insert(cls).values(values)
        await session.execute(stmt)


# ---------------------------------------------------------------------------
#   Base models common.py to main app and archive
# ---------------------------------------------------------------------------
class BaseSensorRecord(Base, Record):
    __abstract__ = True

    id: Mapped[int] = mapped_column(primary_key=True)
    measure: Mapped[int] = mapped_column()
    timestamp: Mapped[datetime] = mapped_column(UtcDateTime)
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


class BaseActuatorRecord(Base, Record):
    __abstract__ = True

    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[str] = mapped_column(sa.String(length=16))
    timestamp: Mapped[datetime] = mapped_column(UtcDateTime)
    mode: Mapped[ActuatorMode] = mapped_column(default=ActuatorMode.automatic)
    status: Mapped[bool] = mapped_column(default=False)

    @declared_attr
    def ecosystem_uid(cls) -> Mapped[str]:
        return mapped_column(
            sa.String(length=8), sa.ForeignKey("ecosystems.uid"), index=True
        )

    @declared_attr
    def actuator_uid(cls) -> Mapped[str]:
        return mapped_column(
            sa.String(length=16), sa.ForeignKey("hardware.uid"), index=True
        )


class BaseHealthRecord(Base, Record):
    __abstract__ = True

    id: Mapped[int] = mapped_column(primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(UtcDateTime)
    green: Mapped[int] = mapped_column()
    necrosis: Mapped[int] = mapped_column()
    health_index: Mapped[int] = mapped_column()

    @declared_attr
    def ecosystem_uid(cls) -> Mapped[str]:
        return mapped_column(
            sa.String(length=8), sa.ForeignKey("ecosystems.uid"), index=True
        )


class BaseWarning(Base):
    __abstract__ = True

    id: Mapped[int] = mapped_column(primary_key=True)
    level: Mapped[WarningLevel] = mapped_column(default=WarningLevel.low)
    title: Mapped[str] = mapped_column(sa.String(length=256))
    description: Mapped[Optional[str]] = mapped_column(sa.String(length=2048))
    created_on: Mapped[datetime] = mapped_column(UtcDateTime, default=datetime.now(timezone.utc))
    seen_on: Mapped[Optional[datetime]] = mapped_column(UtcDateTime)
    solved_on: Mapped[Optional[datetime]] = mapped_column(UtcDateTime)

    @property
    def seen(self):
        return self.seen_on is not None

    @property
    def solved(self):
        return self.solved_on is not None

    @classmethod
    async def create(
            cls,
            session: AsyncSession,
            message_payload: dict,
    ) -> Self:
        msg = cls(**message_payload)
        session.add(msg)
        await session.commit()
        return msg

    @classmethod
    async def get_multiple(
            cls,
            session: AsyncSession,
            max_first: int = 10
    ) -> Sequence[Self]:
        stmt = (
            select(cls)
            .where(cls.solved is False)
            .order_by(cls.created_on.desc())
            .limit(max_first)
        )
        result = await session.execute(stmt)
        return result.scalars().all()
