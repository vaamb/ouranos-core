from sqlalchemy.ext.asyncio import AsyncSession

from ouranos import sdk
from ouranos.core.database.models import anonymous_user, UserMixin


async def get_current_user(session: AsyncSession, telegram_id: int) -> UserMixin:
    user = await sdk.user.get_by_telegram_id(session, telegram_id)
    if user:
        return user
    return anonymous_user


async def activate_user(
        session: AsyncSession,
        user: UserMixin,
        telegram_id: int
) -> None:
    await sdk.user.update(session, user.id, {"telegram_chat_id": telegram_id})

