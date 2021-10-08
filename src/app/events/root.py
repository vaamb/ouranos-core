import logging

from flask import current_app, request
from flask_login import current_user
from flask_socketio import join_room

from src.app import app_name, sio
from src.app.events import dispatcher
from src.models import Ecosystem, Permission


# TODO: change name
sio_logger = logging.getLogger(f"{app_name}.socketio")


# ---------------------------------------------------------------------------
#   SocketIO events
# ---------------------------------------------------------------------------
@sio.on("connect", namespace="/")
def connect_on_browser():
    if any((current_app.config["DEBUG"], current_app.config["TESTING"])):
        remote_addr = request.environ["REMOTE_ADDR"]
        remote_port = request.environ["REMOTE_PORT"]
        sio_logger.debug(f"Connection from {remote_addr}:{remote_port}")


@sio.on("disconnect", namespace="/")
def connect_on_browser():
    if any((current_app.config["DEBUG"], current_app.config["TESTING"])):
        remote_addr = request.environ["REMOTE_ADDR"]
        remote_port = request.environ["REMOTE_PORT"]
        sio_logger.debug(f"Disconnection of {remote_addr}:{remote_port}")


# TODO: move for admin
@sio.on("my_ping", namespace="/")
def ping_pong():
    incoming_sid = request.sid
    sio.emit("my_pong", namespace="/", room=incoming_sid)


@sio.on("turn_light", namespace="/")
def turn_light(message):
    if not current_user.can(Permission.OPERATE):
        return False
    ecosystem_id = message["ecosystem"]
    sid = Ecosystem.query.filter_by(id=ecosystem_id).one().manager.sid
    mode = message.get("mode", "automatic")
    countdown = message.get("countdown", False)
    sio_logger.debug(
        f"Dispatching 'turn_light_{mode}' signal to ecosystem {ecosystem_id}")
    sio.emit("turn_light",
             {"ecosystem": ecosystem_id, "mode": mode, "countdown": countdown},
             namespace="/gaia", room=sid)
    return False


@sio.on("subscribe", namespace="/")
def subscribe(message):
    join_room(message["channel"])
    # Currently available rooms: home, weather, <ecosystem_id>


# ---------------------------------------------------------------------------
#   Dispatcher events
# ---------------------------------------------------------------------------
@dispatcher.on("current_weather")
def _current_weather(*args, **kwargs):
    # TODO: add room "weather"
    #  emit to
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
