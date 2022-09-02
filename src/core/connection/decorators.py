def registration_required(func):
    """Decorator which makes sure the engine is registered and injects
    engine_uid"""
    async def wrapper(self, sid, data):
        async with self.session(sid, namespace="/gaia") as session:
            engine_uid = session.get("engine_uid")
        if not engine_uid:
            await self.disconnect(sid, namespace="/gaia")
        else:
            return await func(self, sid, data, engine_uid)
    return wrapper
