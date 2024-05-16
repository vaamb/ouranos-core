from __future__ import annotations

from abc import abstractmethod
from datetime import datetime, timedelta, timezone
from typing import NamedTuple, Self, Sequence

from sqlalchemy import delete, insert, update
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
    uid: str | int

    @classmethod
    async def create(
            cls,
            session: AsyncSession,
            values: dict | list[dict],
    ) -> None:
        stmt = insert(cls).values(values)
        await session.execute(stmt)

    @classmethod
    async def update(
            cls,
            session: AsyncSession,
            values: dict,
            uid: str | None = None,
    ) -> None:
        uid = uid or values.pop("uid", None)
        if not uid:
            raise ValueError(
                "Provide uid either as a parameter or as a key in the updated info"
            )
        stmt = (
            update(cls)
            .where(cls.uid == uid)
            .values(**values)
        )
        await session.execute(stmt)

    @classmethod
    async def delete(
            cls,
            session: AsyncSession,
            uid: str,
    ) -> None:
        stmt = delete(cls).where(cls.uid == uid)
        await session.execute(stmt)

    @classmethod
    async def update_or_create(
            cls,
            session: AsyncSession,
            values: dict,
            uid: str | None = None,
    ) -> None:
        uid = uid or values.pop("uid", None)
        if not uid:
            raise ValueError(
                "Provide uid either as an argument or as a key in the values"
            )
        obj = await cls.get(session, uid)
        if not obj:
            values["uid"] = uid
            await cls.create(session, values)
        elif values:
            await cls.update(session, values, uid)
        else:
            raise ValueError

    @classmethod
    @abstractmethod
    async def get(
            cls,
            session: AsyncSession,
            uid: str,
    ) -> Self | None:
        raise NotImplementedError

    @classmethod
    @abstractmethod
    async def get_multiple(
            cls,
            session: AsyncSession,
            uid: str | list | None = None,
    ) -> Sequence[Self]:
        raise NotImplementedError


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
