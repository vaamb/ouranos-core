from src.core import api
from src.core.database.models import anonymous_user, UserMixin


async def get_current_user(session, telegram_id) -> UserMixin:
    user = await api.user.get_by_telegram_id(session, telegram_id)
    if user:
        return user
    return anonymous_user
