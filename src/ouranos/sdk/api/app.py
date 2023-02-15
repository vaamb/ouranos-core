from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ouranos.core.database.models.app import FlashMessage, Service


class service:
    @staticmethod
    async def get_multiple(
            session: AsyncSession,
            level: str | list | None = None
    ) -> list[Service]:
        if level is None:
            stmt = select(Service)
        else:
            stmt = select(Service).where(Service.level.in_(level))
        result = await session.execute(stmt)
        return result.scalars().all()


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
