from __future__ import annotations

from abc import abstractmethod
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import NamedTuple, Self, Sequence

from sqlalchemy import and_, delete, insert, inspect, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ouranos import db


class ToDictMixin:
    def to_dict(self, exclude: list | None = None) -> dict:
        exclude: list = exclude or []
        return {
            key: value for key, value in vars(self).items()
            if (
                    key not in exclude
                    and not key.startswith("_")
            )
        }


class Base(db.Model, ToDictMixin):
    __abstract__ = True


class CRUDMixin:
    __primary_keys: list[str] | None = None

    @classmethod
    def _get_primary_keys(cls) -> list[str]:
        if cls.__primary_keys is None:
            cls.__primary_keys = [column.name for column in inspect(cls).primary_key]
        return cls.__primary_keys

    @classmethod
    async def create(
            cls,
            session: AsyncSession,
            /,
            values: dict | list[dict],
    ) -> None:
        stmt = insert(cls).values(values)
        await session.execute(stmt)

    @classmethod
    async def get(
            cls,
            session: AsyncSession,
            /,
            **primary_keys: str | Enum,
    ) -> Self | None:
        for key in cls._get_primary_keys():
            value = primary_keys.get(key)
            if value is None:
                raise ValueError(f"You need to provide '{key}'")
        stmt = (
            select(cls)
            .where(
                and_(
                    cls.__table__.c[key] == value
                    for key, value in primary_keys.items()
                )
            )
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @classmethod
    async def get_multiple(
            cls,
            session: AsyncSession,
            /,
            **primary_keys: list[str | Enum] | str,
    ) -> Sequence[Self]:
        if not primary_keys:
            stmt = select(cls)
            result = await session.execute(stmt)
            return result.scalars().all()

        for key in cls._get_primary_keys():
            value = primary_keys.get(key)
            if value is None:
                raise ValueError(f"You need to provide '{key}'")
            if isinstance(value, str):
                primary_keys[key] = [value]
        stmt = (
            select(cls)
            .where(
                or_(
                    cls.__table__.c[key].in_(value)
                    for key, value in primary_keys.items()
                )
            )
        )
        result = await session.execute(stmt)
        return result.scalars().all()

    @classmethod
    async def update(
            cls,
            session: AsyncSession,
            /,
            values: dict,
            **primary_keys: str | Enum,
    ) -> None:
        for key in cls._get_primary_keys():
            value = primary_keys.get(key) or values.pop(key, None)
            if value is None:
                raise ValueError(
                    f"Provide '{key}' either as a parameter or as a key in the "
                    f"updated info")
            primary_keys[key] = value
        stmt = (
            update(cls)
            .where(
                and_(
                    cls.__table__.c[key] == value
                    for key, value in primary_keys.items()
                )
            )
            .values(**values)
        )
        await session.execute(stmt)

    @classmethod
    async def delete(
            cls,
            session: AsyncSession,
            /,
            **primary_keys: str | Enum,
    ) -> None:
        stmt = (
            delete(cls)
            .where(
                and_(
                    cls.__table__.c[key] == value
                    for key, value in primary_keys.items()
                )
            )
        )
        await session.execute(stmt)

    @classmethod
    async def update_or_create(
            cls,
            session: AsyncSession,
            /,
            values: dict,
            **primary_keys: str | Enum,
    ) -> None:
        for key in cls._get_primary_keys():
            value = primary_keys.get(key) or values.pop(key, None)
            if value is None:
                raise ValueError(
                    f"Provide '{key}' either as a parameter or as a key in the "
                    f"updated info")
            primary_keys[key] = value
        obj = await cls.get(session, **primary_keys)
        if not obj:
            values.update(primary_keys)
            await cls.create(session, values=values)
        elif values:
            await cls.update(session, values=values, **primary_keys)

class RecordMixin:
    @classmethod
    async def create_records(
            cls,
            session: AsyncSession,
            values: dict | list[dict] | list[NamedTuple],
    ) -> None:
        stmt = insert(cls).values(values)
        await session.execute(stmt)

    @classmethod
    @abstractmethod
    async def get_records(
            cls,
            session: AsyncSession,
            **kwargs
    ) -> Sequence[Self]:
        raise NotImplementedError


class CacheMixin:
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
