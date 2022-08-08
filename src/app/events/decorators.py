import functools
from flask_login import current_user
from flask_socketio import disconnect


def permission_required(permission):
    def decorator(func):
        @functools.wraps(func)
        def wrapped(*args, **kwargs):
            if not current_user.can(permission):
                pass
                disconnect()
            else:
                return func(*args, **kwargs)
        return wrapped
    return decorator
