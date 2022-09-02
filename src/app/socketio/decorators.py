import functools

from . import sio


def permission_required(permission: int):
    def decorator(func):
        @functools.wraps(func)
        def wrapped(sid, data):
            if not 0:
                pass
            else:
                return func(sid, data)
        return wrapped
    return decorator
