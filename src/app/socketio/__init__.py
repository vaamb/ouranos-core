from socketio import AsyncServer, ASGIApp

sio = AsyncServer(async_mode='asgi', cors_allowed_origins=[])
asgi_app = ASGIApp(sio)

from . import clients  # noqa  # import sio routes
