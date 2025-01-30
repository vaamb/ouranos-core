from __future__ import annotations

from abc import abstractmethod
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import NamedTuple, Self, Sequence
from uuid import UUID

from sqlalchemy import and_, delete, insert, inspect, Select, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ouranos import db


lookup_keys_type: str | Enum | UUID | bool


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
    def _check_lookup_keys(cls, *lookup_keys: str) -> None:
        valid_lookup_keys = cls._get_lookup_keys()
        if not all(lookup_key in lookup_keys for lookup_key in valid_lookup_keys):
            raise ValueError("You should provide all the lookup keys")

    @classmethod
    async def create(
            cls,
            session: AsyncSession,
            /,
            values: dict | None = None,
            **lookup_keys: lookup_keys_type,
    ) -> None:
        cls._check_lookup_keys(*lookup_keys.keys())
        values = values or {}
        stmt = insert(cls).values(**lookup_keys, **values)
        await session.execute(stmt)

    @classmethod
    async def create_multiple(
            cls,
            session: AsyncSession,
            /,
            values: list[dict],
    ) -> None:
        stmt = insert(cls).values(values)
        await session.execute(stmt)

    @classmethod
    def _generate_get_query(
            cls,
            offset: int | None = None,
            limit: int | None = None,
            order_by: str | None = None,
            **lookup_keys: list[lookup_keys_type] | lookup_keys_type | None,
    ) -> Select:
        stmt = select(cls)
        for key, value in lookup_keys.items():
            if value is None:
                continue
            if isinstance(value, list):
                stmt = stmt.where(cls.__table__.c[key].in_(value))
            else:
                stmt = stmt.where(cls.__table__.c[key] == value)
        if offset is not None:
            stmt = stmt.offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)
        if order_by is not None:
            stmt = stmt.order_by(order_by)
        return stmt

    @classmethod
    async def get(
            cls,
            session: AsyncSession,
            /,
            **lookup_keys: lookup_keys_type | None,
    ) -> Self | None:
        """
        :param session: an AsyncSession instance
        :param lookup_keys: a dict with table column names as keys and values
                            depending on the related column data type
        """
        stmt = cls._generate_get_query(**lookup_keys)
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
            **lookup_keys: list[lookup_keys_type] | lookup_keys_type | None,
    ) -> Sequence[Self]:
        """
        :param session: an AsyncSession instance
        :param offset: the offset from which to start looking
        :param limit: the maximum number of rows to query
        :param order_by: how to order the results
        :param lookup_keys: a dict with table column names as keys and values
                            depending on the related column data type
        """
        stmt = cls._generate_get_query(**lookup_keys)
        result = await session.execute(stmt)
        return result.scalars().all()

    @classmethod
    async def update(
            cls,
            session: AsyncSession,
            /,
            values: dict,
            **lookup_keys: lookup_keys_type,
    ) -> None:
        cls._check_lookup_keys(*lookup_keys.keys())
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
    async def update_multiple(
            cls,
            session: AsyncSession,
            /,
            values: list[dict],
    ) -> None:
        await session.execute(
            update(cls),
            values
        )

    @classmethod
    async def delete(
            cls,
            session: AsyncSession,
            /,
            **lookup_keys: lookup_keys_type,
    ) -> None:
        cls._check_lookup_keys(*lookup_keys.keys())
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
            values: dict | None = None,
            **lookup_keys: lookup_keys_type,
    ) -> None:
        #cls._check_lookup_keys(*lookup_keys.keys())
        obj = await cls.get(session, **lookup_keys)
        if not obj:
            await cls.create(session, values=values, **lookup_keys)
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
