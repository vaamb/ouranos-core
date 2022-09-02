from __future__ import annotations

import typing as t

from sqlalchemy.ext.asyncio import AsyncSession

from core.database import CustomMeta  # noqa


class Base:
    @staticmethod
    async def create(
            session: AsyncSession,
            info: dict,
    ) -> CustomMeta:
        raise NotImplementedError

    @staticmethod
    async def update(
            session: AsyncSession,
            info: dict,
            uid: t.Optional[str] = None,
    ) -> None:
        raise NotImplementedError

    @staticmethod
    async def delete(
            session: AsyncSession,
            uid: str,
    ) -> None:
        raise NotImplementedError

    @staticmethod
    async def get(
            session: AsyncSession,
            uids: t.Optional[str | tuple | list],
    ) -> list[CustomMeta]:
        """Return fmt: result.scalars().all()"""
        raise NotImplementedError

    @staticmethod
    async def get_one(
            session: AsyncSession,
            uid: str,
    ) -> CustomMeta:
        """Return fmt: result.scalars().one_or_none()"""
        raise NotImplementedError
