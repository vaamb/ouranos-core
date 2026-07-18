import functools

from ouranos import db
from ouranos.core.database.models.app import Permission
from ouranos.web_server.auth import login_manager


def permission_required(permission: Permission):
    def decorator(func):
        @functools.wraps(func)
        async def wrapped(self, sid, data):
            session = await self.get_session(sid)
            user_id = session.get('user_id', None)
            async with db.scoped_session() as db_session:
                user = await login_manager.get_user(db_session, user_id)
            if user.can(permission):
                return await func(self, sid, data)
            return
        return wrapped
    return decorator
