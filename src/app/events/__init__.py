from __future__ import annotations

import logging

from dispatcher import AsyncDispatcher
from socketio import AsyncNamespace

from .decorators import permission_required
from src.app.factory import dispatcher, sio_manager
from src.core import api
from src.core.g import config, db


# TODO: change name
sio_logger = logging.getLogger(f"{config['APP_NAME'].lower()}.socketio")


class Events(AsyncNamespace):
    # ---------------------------------------------------------------------------
    #   SocketIO socketio
    # ---------------------------------------------------------------------------
    def __init__(self, namespace=None):
        super().__init__(namespace=namespace)
        self._dispatcher: AsyncDispatcher | None = None

    @property
    def dispatcher(self) -> AsyncDispatcher:
        if not self._dispatcher:
            raise RuntimeError("You need to set dispatcher")
        return self._dispatcher

    @dispatcher.setter
    def dispatcher(self, dispatcher: AsyncDispatcher):
        self._dispatcher = dispatcher

    async def on_ping(self, sid, data):
        await self.emit("pong", namespace="/", room=sid)

    # @permission_required(Permission.OPERATE)
    async def on_turn_light(self, sid, data):
        ecosystem_uid = data["ecosystem"]
        with db.scoped_session() as session:
            ecosystem = await api.ecosystem.get(session, ecosystem_uid)
        if not ecosystem:
            return
        ecosystem_sid = ecosystem.engine.sid
        mode = data.get("mode", "automatic")
        countdown = data.get("countdown", False)
        sio_logger.debug(
            f"Dispatching 'turn_light' signal to ecosystem {ecosystem_uid}")
        # TODO: use api
        await self.dispatcher.emit(
            event="turn_light",
            data={"ecosystem": ecosystem_uid, "mode": mode, "countdown": countdown},
            room=ecosystem_sid,
            namespace="aggregator",
        )

    # @permission_required(Permission.OPERATE)
    async def on_manage_ecosystem(self, sid, data):
        ecosystem_uid = data["ecosystem"]
        with db.scoped_session() as session:
            ecosystem = await api.ecosystem.get(session, ecosystem_uid)
        if not ecosystem:
            return
        ecosystem_sid = ecosystem.engine.sid
        management = data["management"]
        status = data["status"]
        # TODO: use api
        await self.dispatcher.emit(
            event="change_management",
            data={
                "ecosystem": ecosystem_uid, "management": management, "status": status
            },
            namespace="aggregator",
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


# ---------------------------------------------------------------------------
#   Dispatcher socketio
# ---------------------------------------------------------------------------
@dispatcher.on("weather_current")
async def _current_weather(**kwargs):
    await sio_manager.emit("weather_current", namespace="/", **kwargs)


@dispatcher.on("weather_hourly")
async def _hourly_weather(**kwargs):
    await sio_manager.emit("weather_hourly", namespace="/", **kwargs)


@dispatcher.on("weather_daily")
async def _daily_weather(**kwargs):
    await sio_manager.emit("weather_daily", namespace="/", **kwargs)


@dispatcher.on("sun_times")
async def _sun_times(**kwargs):
    await sio_manager.emit("sun_times", namespace="/", **kwargs)


# TODO: move this in aggregator?
@dispatcher.on("current_server_data")
async def _current_server_data(data):
    api.system.update_current_data(data)
    await sio_manager.emit("current_server_data", data=data, namespace="/")


# Redispatch events coming from dispatcher to clients
@dispatcher.on("ecosystem_status")
async def _ecosystem_status(data):
    await sio_manager.emit("ecosystem_status", data=data, namespace="/")


@dispatcher.on("current_sensors_data")
async def _current_sensors_data(data):
    await sio_manager.emit("current_sensors_data", data=data, namespace="/")


@dispatcher.on("light_data")
async def _current_sensors_data(data):
    await sio_manager.emit("light_data", data=data, namespace="/")
