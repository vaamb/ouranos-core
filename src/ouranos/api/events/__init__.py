from __future__ import annotations

import logging

from dispatcher import AsyncDispatcher, AsyncEventHandler
from socketio import AsyncNamespace

from .decorators import permission_required
from ouranos.api.factory import sio_manager
from ouranos import current_app, db, sdk


# TODO: change name
sio_logger = logging.getLogger(f"{current_app.config['APP_NAME'].lower()}.socketio")


class ClientEvents(AsyncNamespace):
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

    # ---------------------------------------------------------------------------
    #   Events Clients -> Api -> Aggregator
    # ---------------------------------------------------------------------------
    # @permission_required(Permission.OPERATE)
    async def on_turn_light(self, sid, data):
        ecosystem_uid = data["ecosystem"]
        with db.scoped_session() as session:
            ecosystem = await sdk.ecosystem.get(session, ecosystem_uid)
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
            ecosystem = await sdk.ecosystem.get(session, ecosystem_uid)
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
            self.dispatcher.emit("functionalities", "start_service", service)
        else:
            self.dispatcher.emit("functionalities", "stop_service", service)


class DispatcherEvents(AsyncEventHandler):
    # ---------------------------------------------------------------------------
    #   Events Functionalities -> Api -> Clients
    # ---------------------------------------------------------------------------
    async def on_weather_current(self, sid, data):
        await sio_manager.emit("weather_current", data=data, namespace="/")

    async def on_weather_hourly(self, sid, data):
        await sio_manager.emit("weather_hourly", data=data, namespace="/")

    async def on_weather_daily(self, sid, data):
        await sio_manager.emit("weather_daily", data=data, namespace="/")

    async def on_sun_times(self, sid, data):
        await sio_manager.emit("sun_times", data=data, namespace="/")

    # ---------------------------------------------------------------------------
    #   Events Aggregator -> Api -> Clients
    # ---------------------------------------------------------------------------
    async def on_current_server_data(self, sid, data):
        await sio_manager.emit("current_server_data", data=data, namespace="/")

    async def on_ecosystem_status(self, sid, data):
        await sio_manager.emit("ecosystem_status", data=data, namespace="/")

    async def on_current_sensors_data(self, sid, data):
        await sio_manager.emit("current_sensors_data", data=data, namespace="/")

    async def on_light_data(self, sid, data):
        await sio_manager.emit("light_data", data=data, namespace="/")
