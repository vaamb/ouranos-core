import functools

from src.app import sio


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


def registration_required(func):
    """Decorator which makes sure the engine is registered and injects
    engine_uid"""
    async def wrapper(sid, data):
        async with sio.session(sid, namespace="/gaia") as session:
            engine_uid = session.get("engine_uid")
        if not engine_uid:
            await sio.disconnect(sid, namespace="/gaia")
        else:
            return await func(sid, data, engine_uid)
    return wrapper
