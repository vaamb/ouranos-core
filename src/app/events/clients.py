import logging

from flask import request
from sqlalchemy import select

from .decorators import permission_required
from .shared_resources import dispatcher
from src.app import app_name, db, sio
from src.cache import systemData
from src.database.models.app import Permission
from src.database.models.gaia import Ecosystem


# TODO: change name
sio_logger = logging.getLogger(f"{app_name.lower()}.socketio")


# ---------------------------------------------------------------------------
#   SocketIO events
# ---------------------------------------------------------------------------
@sio.on("my_ping", namespace="/")
def ping_pong():
    incoming_sid = request.sid
    sio.emit("my_pong", namespace="/", room=incoming_sid)


@sio.on("turn_light", namespace="/")
@permission_required(Permission.OPERATE)
def turn_light(message):
    ecosystem_id = message["ecosystem"]
    sid = Ecosystem.query.filter_by(id=ecosystem_id).one().engine.sid
    mode = message.get("mode", "automatic")
    countdown = message.get("countdown", False)
    sio_logger.debug(
        f"Dispatching 'turn_light' signal to ecosystem {ecosystem_id}")
    sio.emit(
        "turn_light",
        {"ecosystem": ecosystem_id, "mode": mode, "countdown": countdown},
        namespace="/gaia",
        room=sid
    )


@sio.on("manage_ecosystem", namespace="/")
@permission_required(Permission.OPERATE)
def manage_engine(message):
    print(message)
    ecosystem_id = message["ecosystem"]
    query = select(Ecosystem).where(Ecosystem.uid == ecosystem_id)
    sid = db.session.execute(query).scalars().one().engine.sid
    management = message["management"]
    status = message["status"]
    sio.emit(
        "change_management",
        {"ecosystem": ecosystem_id, "management": management, "status": status},
        namespace="/gaia",
        room=sid
    )


@sio.on("manage_service", namespace="/")
@permission_required(Permission.ADMIN)
def start_service(message):
    service = message["service"]
    status = message["status"]
    if status:
        dispatcher.emit("services", "start_service", service)
    else:
        dispatcher.emit("services", "stop_service", service)


# ---------------------------------------------------------------------------
#   Dispatcher events
# ---------------------------------------------------------------------------
@dispatcher.on("weather_current")
def _current_weather(**kwargs):
    sio.emit("weather_current", namespace="/", **kwargs)


@dispatcher.on("weather_hourly")
def _hourly_weather(**kwargs):
    sio.emit("weather_hourly", namespace="/", **kwargs)


@dispatcher.on("weather_daily")
def _daily_weather(**kwargs):
    sio.emit("weather_daily", namespace="/", **kwargs)


@dispatcher.on("sun_times")
def _sun_times(**kwargs):
    sio.emit("sun_times", namespace="/", **kwargs)


@dispatcher.on("current_server_data")
def _current_server_data(data):
    systemData.update(data)
    sio.emit(event="current_server_data", data=data, namespace="/")
