from __future__ import annotations

from abc import abstractmethod
from datetime import datetime, timedelta, timezone
from typing import Optional, Self, Sequence

from sqlalchemy import delete, insert, Row, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.functions import max as sa_max

from ouranos import current_app
from ouranos.core.database.models.common import BaseSensorData, BaseSystemData


class DbCache:
    timestamp: datetime

    @classmethod
    @abstractmethod
    def get_ttl(cls) -> int:
        """Return data TTL in seconds"""
        raise NotImplementedError

    @classmethod
    async def insert_data(
            cls,
            session: AsyncSession,
            values: dict | list[dict]
    ) -> None:
        await cls.remove_expired(session)
        stmt = insert(cls).values(values)
        await session.execute(stmt)

    @classmethod
    @abstractmethod
    async def get_recent(
            cls,
            session: AsyncSession,
            **kwargs
    ) -> Sequence[Self]:
        """Must start by calling `await cls.remove_expired(session)`"""
        raise NotImplementedError

    @classmethod
    async def remove_expired(cls, session: AsyncSession) -> None:
        time_limit = datetime.now(timezone.utc) - timedelta(seconds=cls.get_ttl())
        stmt = delete(cls).where(cls.timestamp < time_limit)
        await session.execute(stmt)

    @classmethod
    async def clear(cls, session: AsyncSession) -> None:
        stmt = delete(cls)
        await session.execute(stmt)


class SensorDbCache(BaseSensorData, DbCache):
    __tablename__ = "sensor_temp"
    __bind_key__ = "memory"

    @classmethod
    def get_ttl(cls) -> int:
        return current_app.config["ECOSYSTEM_TIMEOUT"]

    @classmethod
    async def get_recent(
            cls,
            session: AsyncSession,
            ecosystem_uid: str | list | None = None,
            sensor_uid: str | list | None = None,
            measure: str | list | None = None,
    ) -> Sequence[Self]:
        await cls.remove_expired(session)
        sub_stmt = (
            select(cls.id, sa_max(cls.timestamp))
            .group_by(cls.sensor_uid, cls.measure)
            .subquery()
        )
        stmt = select(cls).join(sub_stmt, cls.id == sub_stmt.c.id)

        local_vars = locals()
        args = "ecosystem_uid", "sensor_uid", "measure"
        for arg in args:
            value = local_vars.get(arg)
            if value:
                if isinstance(value, str):
                    value = value.split(",")
                hardware_attr = getattr(cls, arg)
                stmt = stmt.where(hardware_attr.in_(value))
        result = await session.execute(stmt)
        return result.scalars().all()

    @classmethod
    async def get_recent_timed_values(
            cls,
            session: AsyncSession,
            sensor_uid: str,
            measure: str,
    ) -> list[tuple[datetime, float]]:
        await cls.remove_expired(session)
        sub_stmt = (
            select(cls.id, sa_max(cls.timestamp))
            .group_by(cls.sensor_uid, cls.measure)
            .subquery()
        )
        stmt = (
            select(cls.timestamp, cls.value)
            .join(sub_stmt, cls.id == sub_stmt.c.id)
            .where(cls.sensor_uid == sensor_uid)
            .where(cls.measure == measure)
        )
        result = await session.execute(stmt)
        #
        return [r._data for r in result.all()]


class SystemDbCache(BaseSystemData, DbCache):
    __tablename__ = "system_temp"
    __bind_key__ = "memory"

    @classmethod
    def get_ttl(cls) -> int:
        return 90

    @classmethod
    async def get_recent(
            cls,
            session: AsyncSession,
            system_uid: str | list | None = None
    ) -> Sequence[Self]:
        await cls.remove_expired(session)
        sub_stmt = (
            select(cls.id, sa_max(cls.timestamp))
            .group_by(cls.system_uid)
            .subquery()
        )
        stmt = select(cls).join(sub_stmt, cls.id == sub_stmt.c.id)
        if system_uid:
            if isinstance(system_uid, str):
                system_uid = [system_uid, ]
            stmt = stmt.where(cls.system_uid.in_(system_uid))
        result = await session.execute(stmt)
        return result.scalars().all()

    @classmethod
    async def get_recent_timed_values(
            cls,
            session: AsyncSession,
            system_uid: str | list | None = None
    ) -> list[
        tuple[datetime, str, float, Optional[float], float, float, float,
              float, float]
    ]:
        await cls.remove_expired(session)
        sub_stmt = (
            select(cls.id, sa_max(cls.timestamp))
            .group_by(cls.system_uid)
            .subquery()
        )
        stmt = select(
            cls.timestamp, cls.system_uid, cls.CPU_used, cls.CPU_temp,
            cls.RAM_process, cls.RAM_used, cls.RAM_total, cls.DISK_used,
            cls.DISK_total
        ).join(sub_stmt, cls.id == sub_stmt.c.id)
        if system_uid:
            if isinstance(system_uid, str):
                system_uid = [system_uid, ]
            stmt = stmt.where(cls.system_uid.in_(system_uid))
        result = await session.execute(stmt)
        return [r._data for r in result.all()]
