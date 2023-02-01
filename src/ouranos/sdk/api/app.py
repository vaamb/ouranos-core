from __future__ import annotations

import typing as t

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ouranos.core.database.models.app import FlashMessage, Service


class service:
    @staticmethod
    async def get_multiple(
            session: AsyncSession,
            level: t.Optional[list | tuple | str] = None
    ) -> list[Service]:
        if level is None or "all" in level:
            stmt = select(Service)
        else:
            stmt = select(Service).where(Service.level.in_(level))
        result = await session.execute(stmt)
        return result.scalars().all()

    @staticmethod
    def get_info(
            services: Service | list[Service]
    ):
        if isinstance(services, Service):
            services = [services]
        return [s.to_dict() for s in services]


class flash_message:
    @staticmethod
    async def create(
            session: AsyncSession,
            message_payload: dict,
    ) -> FlashMessage:
        msg = FlashMessage(**message_payload)
        session.add(msg)
        await session.commit()
        return msg

    @staticmethod
    async def get_multiple(
            session: AsyncSession,
            max_first: int = 10
    ) -> list[FlashMessage]:
        stmt = (
            select(FlashMessage)
            .where(FlashMessage.solved is False)
            .order_by(FlashMessage.created_on.desc())
            .limit(max_first)
        )
        result = await session.execute(stmt)
        return result.scalars().all()

    @staticmethod
    def get_content(
            flash_messages: FlashMessage | list[FlashMessage]
    ) -> list[str]:
        if isinstance(flash_messages, FlashMessage):
            flash_messages = [flash_messages]
        return [msg.description for msg in flash_messages]
