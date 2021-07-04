from app import sio
from app.events import dispatcher


@dispatcher.on("turn_light")
def _turn_light(*args, **kwargs):
    sio.emit("turn_light", namespace="/gaia", **kwargs)
