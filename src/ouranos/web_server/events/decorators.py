import functools

from ouranos import db
from ouranos.core.database.models.app import Permission
from ouranos.core.exceptions import NotAuthorized
from ouranos.web_server.user_session import get_user_from_session_info


def permission_required(permission: Permission):
    def decorator(func):
        @functools.wraps(func)
        async def wrapped(self, sid, data):
            session = await self.get_session(sid)
            session_info = session.get("session_info", None)
            async with db.scoped_session() as db_session:
                user = await get_user_from_session_info(db_session, session_info)
            if user.can(permission):
                return await func(self, sid, data)
            event: str = func.__name__[3:]
            self.logger.debug(f'sid: {sid} - "SocketIO {event}" not authorized')
            raise NotAuthorized()
        return wrapped
    return decorator
