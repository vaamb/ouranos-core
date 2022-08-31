import logging

from .decorators import permission_required
from src import api
from src.app import db, dispatcher, sio
from src.app.utils import app_config
from src.cache import systemData


# TODO: change name
sio_logger = logging.getLogger(f"{app_config['APP_NAME'].lower()}.socketio")


# ---------------------------------------------------------------------------
#   SocketIO events
# ---------------------------------------------------------------------------
@sio.on("my_ping", namespace="/")
async def ping_pong(sid, data):
    sio.emit("my_pong", namespace="/", room=sid)


@sio.on("turn_light", namespace="/")  # TODO: change to turn actuator
# @permission_required(Permission.OPERATE)
async def turn_light(sid, data):
    ecosystem_uid = data["ecosystem"]
    with db.scoped_session() as session:
        ecosystem = await api.gaia.get_ecosystem(session, ecosystem_uid)
    if not ecosystem:
        return
    ecosystem_sid = ecosystem.engine.sid
    mode = data.get("mode", "automatic")
    countdown = data.get("countdown", False)
    sio_logger.debug(
        f"Dispatching 'turn_light' signal to ecosystem {ecosystem_uid}")
    sio.emit(
        event="turn_light",
        data={"ecosystem": ecosystem_uid, "mode": mode, "countdown": countdown},
        room=ecosystem_sid,
        namespace="/gaia",
    )


@sio.on("manage_ecosystem", namespace="/")
# @permission_required(Permission.OPERATE)
async def manage_engine(sid, data):
    ecosystem_uid = data["ecosystem"]
    with db.scoped_session() as session:
        ecosystem = await api.gaia.get_ecosystem(session, ecosystem_uid)
    if not ecosystem:
        return
    ecosystem_sid = ecosystem.engine.sid
    management = data["management"]
    status = data["status"]
    sio.emit(
        event="change_management",
        data={
            "ecosystem": ecosystem_uid, "management": management, "status": status
        },
        namespace="/gaia",
        room=ecosystem_sid
    )


@sio.on("manage_service", namespace="/")
# @permission_required(Permission.ADMIN)
def start_service(sid, data):
    service = data["service"]
    status = data["status"]
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
    api.system.update_current_system_data(data)
    sio.emit(event="current_server_data", data=data, namespace="/")
