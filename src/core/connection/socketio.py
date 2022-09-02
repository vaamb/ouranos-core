from socketio import AsyncServer, ASGIApp

sio = AsyncServer(async_mode='asgi', cors_allowed_origins=[])
asgi_app = ASGIApp(socketio_server=sio)

from . import events  # noqa
