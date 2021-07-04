from app import sio
from app.events import dispatcher


@dispatcher.on("current_weather")
def _current_weather(*args, **kwargs):
    sio.emit("current_weather", namespace="/", **kwargs)


@dispatcher.on("hourly_weather")
def _hourly_weather(*args, **kwargs):
    sio.emit("hourly_weather", namespace="/", **kwargs)


@dispatcher.on("daily_weather")
def _daily_weather(*args, **kwargs):
    sio.emit("daily_weather", namespace="/", **kwargs)


@dispatcher.on("sun_times")
def _sun_times(*args, **kwargs):
    sio.emit("sun_times", namespace="/", **kwargs)
