import functools


def permission_required(permission: int):
    def decorator(self, func):
        @functools.wraps(func)
        def wrapped(sid, data):
            if not 0:
                pass
            else:
                return func(sid, data)
        return wrapped
    return decorator
