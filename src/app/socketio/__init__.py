import logging

from socketio import AsyncNamespace

from .decorators import permission_required
from src.app import db, dispatcher
from src.app.utils import app_config
from src.core import api


# TODO: change name
sio_logger = logging.getLogger(f"{app_config['APP_NAME'].lower()}.socketio")


class Events(AsyncNamespace):
    # ---------------------------------------------------------------------------
    #   SocketIO socketio
    # ---------------------------------------------------------------------------
    async def on_my_ping(self, sid, data):
        await self.emit("my_pong", namespace="/", room=sid)

    # @permission_required(Permission.OPERATE)
    async def on_turn_light(self, sid, data):
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
        await self.emit(
            event="turn_light",
            data={"ecosystem": ecosystem_uid, "mode": mode, "countdown": countdown},
            room=ecosystem_sid,
            namespace="/gaia",
        )

# @permission_required(Permission.OPERATE)
    async def on_manage_ecosystem(self, sid, data):
        ecosystem_uid = data["ecosystem"]
        with db.scoped_session() as session:
            ecosystem = await api.gaia.get_ecosystem(session, ecosystem_uid)
        if not ecosystem:
            return
        ecosystem_sid = ecosystem.engine.sid
        management = data["management"]
        status = data["status"]
        await self.emit(
            event="change_management",
            data={
                "ecosystem": ecosystem_uid, "management": management, "status": status
            },
            namespace="/gaia",
            room=ecosystem_sid
        )

    # @permission_required(Permission.ADMIN)
    def on_start_service(self, sid, data):
        service = data["service"]
        status = data["status"]
        if status:
            dispatcher.emit("services", "start_service", service)
        else:
            dispatcher.emit("services", "stop_service", service)

"""
# ---------------------------------------------------------------------------
#   Dispatcher socketio
# ---------------------------------------------------------------------------
@dispatcher.on("weather_current")
def _current_weather(**kwargs):
    # TODO: create async dispatcher or wrap in async_to_sync
    sio.emit("weather_current", namespace="/", **kwargs)


@dispatcher.on("weather_hourly")
def _hourly_weather(**kwargs):
    # TODO: create async dispatcher or wrap in async_to_sync
    sio.emit("weather_hourly", namespace="/", **kwargs)


@dispatcher.on("weather_daily")
def _daily_weather(**kwargs):
    # TODO: create async dispatcher or wrap in async_to_sync
    sio.emit("weather_daily", namespace="/", **kwargs)


@dispatcher.on("sun_times")
def _sun_times(**kwargs):
    # TODO: create async dispatcher or wrap in async_to_sync
    sio.emit("sun_times", namespace="/", **kwargs)


@dispatcher.on("current_server_data")
def _current_server_data(data):
    # TODO: create async dispatcher or wrap in async_to_sync
    api.system.update_current_system_data(data)
    sio.emit(event="current_server_data", data=data, namespace="/")
"""