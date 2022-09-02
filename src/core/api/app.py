from __future__ import annotations

import typing as t

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database.models.app import FlashMessage, Service


async def get_services(
        session: AsyncSession,
        level: t.Optional[list | tuple | str] = None
) -> list[dict]:
    if level is None or "all" in level:
        stmt = select(Service)
    else:
        stmt = select(Service).where(Service.level.in_(level))
    result = await session.execute(stmt)
    services: list[Service] = result.scalars().all()
    return [service.to_dict() for service in services]


async def create_flash_message(
        session: AsyncSession,
        message_payload: dict,
) -> FlashMessage:
    msg = FlashMessage(**message_payload)
    session.add(msg)
    await session.commit()
    return msg


async def get_flash_messages_contents(
        session: AsyncSession,
) -> list[str]:
    stmt = (
        select(FlashMessage)
        .where(FlashMessage.is_solved is False)
        .order_by(FlashMessage.created.desc())
    )
    result = await session.execute(stmt)
    msgs: list[FlashMessage] = result.scalars().all()
    return [msg.content_only() for msg in msgs]
