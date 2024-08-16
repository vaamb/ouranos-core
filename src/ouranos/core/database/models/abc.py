from __future__ import annotations

from abc import abstractmethod
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, NamedTuple, Self, Sequence

from sqlalchemy import and_, delete, insert, inspect, or_, select, update
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
    _lookup_keys: list[str] | None = None

    @classmethod
    def _get_lookup_keys(cls) -> list[str]:
        if cls._lookup_keys is None:
            cls._lookup_keys = [column.name for column in inspect(cls).primary_key]
        return cls._lookup_keys

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
            **lookup_keys: str | Enum,
    ) -> Self | None:
        for key in cls._get_lookup_keys():
            value = lookup_keys.get(key)
            if value is None:
                raise ValueError(f"You need to provide '{key}'")
        stmt = (
            select(cls)
            .where(
                and_(
                    cls.__table__.c[key] == value
                    for key, value in lookup_keys.items()
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
            offset: int | None = None,
            limit: int | None = None,
            order_by: str | None = None,
            **lookup_keys: list[str | Enum] | str,
    ) -> Sequence[Self]:
        valid_lookup_keys = {}
        for key in cls._get_lookup_keys():
            value = lookup_keys.get(key, None)
            if value is None:
                continue
            if isinstance(value, str):
                value = [value]
            valid_lookup_keys[key] = value

        if not valid_lookup_keys:
            stmt = select(cls)
            result = await session.execute(stmt)
            return result.scalars().all()

        stmt = (
            select(cls)
            .where(
                or_(
                    cls.__table__.c[key].in_(value)
                    for key, value in valid_lookup_keys.items()
                )
            )
        )
        if offset is not None:
            stmt = stmt.offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)
        if order_by is not None:
            stmt = stmt.order_by(order_by)
        result = await session.execute(stmt)
        return result.scalars().all()

    @classmethod
    async def update(
            cls,
            session: AsyncSession,
            /,
            values: dict,
            **lookup_keys: str | Enum,
    ) -> None:
        for key in cls._get_lookup_keys():
            value = lookup_keys.get(key) or values.pop(key, None)
            if value is None:
                raise ValueError(
                    f"Provide '{key}' either as a parameter or as a key in the "
                    f"updated info")
            lookup_keys[key] = value
        stmt = (
            update(cls)
            .where(
                and_(
                    cls.__table__.c[key] == value
                    for key, value in lookup_keys.items()
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
            **lookup_keys: str | Enum,
    ) -> None:
        stmt = (
            delete(cls)
            .where(
                and_(
                    cls.__table__.c[key] == value
                    for key, value in lookup_keys.items()
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
            **lookup_keys: str | Enum,
    ) -> None:
        for key in cls._get_lookup_keys():
            value = lookup_keys.get(key) or values.pop(key, None)
            if value is None:
                raise ValueError(
                    f"Provide '{key}' either as a parameter or as a key in the "
                    f"updated info")
            lookup_keys[key] = value
        obj = await cls.get(session, **lookup_keys)
        if not obj:
            values.update(lookup_keys)
            await cls.create(session, values=values)
        elif values:
            await cls.update(session, values=values, **lookup_keys)

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
