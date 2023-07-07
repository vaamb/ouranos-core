from __future__ import annotations

from logging import getLogger, Logger

from dispatcher import AsyncDispatcher, AsyncEventHandler
from socketio import AsyncNamespace, BaseManager

from ouranos import db
from ouranos.core.database.models import Ecosystem
from ouranos.web_server.events.decorators import permission_required


logger: Logger = getLogger(f"aggregator.socketio")


class ClientEvents(AsyncNamespace):
    def __init__(self, namespace=None):
        super().__init__(namespace=namespace)
        self._ouranos_dispatcher: AsyncDispatcher | None = None

    @property
    def ouranos_dispatcher(self) -> AsyncDispatcher:
        if not self._ouranos_dispatcher:
            raise RuntimeError("You need to set the Ouranos event dispatcher")
        return self._ouranos_dispatcher

    @ouranos_dispatcher.setter
    def ouranos_dispatcher(self, dispatcher: AsyncDispatcher):
        self._ouranos_dispatcher = dispatcher

    async def on_ping(self, sid):
        await self.emit("pong", namespace="/", room=sid)

    # ---------------------------------------------------------------------------
    #   Events Clients ->  Web server -> Aggregator
    # ---------------------------------------------------------------------------
    # @permission_required(Permission.OPERATE)
    async def on_turn_light(self, sid, data):
        ecosystem_uid = data["ecosystem"]
        with db.scoped_session() as session:
            ecosystem = await Ecosystem.get(session, ecosystem_uid)
        if not ecosystem:
            return
        ecosystem_sid = ecosystem.engine.sid
        mode = data.get("mode", "automatic")
        countdown = data.get("countdown", False)
        logger.debug(
            f"Dispatching 'turn_light' signal to ecosystem {ecosystem_uid}"
        )
        await self.ouranos_dispatcher.emit(
            event="turn_light",
            data={"ecosystem": ecosystem_uid, "mode": mode, "countdown": countdown},
            room=ecosystem_sid,
            namespace="aggregator",
        )

    # @permission_required(Permission.OPERATE)
    async def on_manage_ecosystem(self, sid, data):
        ecosystem_uid = data["ecosystem"]
        with db.scoped_session() as session:
            ecosystem = await Ecosystem.get(session, ecosystem_uid)
        if not ecosystem:
            return
        ecosystem_sid = ecosystem.engine.sid
        management = data["management"]
        status = data["status"]
        logger.debug(
            f"Dispatching change management '{management}' to status "
            f"'{status}' in ecosystem {ecosystem_uid}"
        )
        await self.ouranos_dispatcher.emit(
            event="change_management",
            data={
                "ecosystem": ecosystem_uid, "management": management, "status": status
            },
            namespace="aggregator",
            room=ecosystem_sid
        )


class DispatcherEvents(AsyncEventHandler):
    def __init__(self, sio_manager: BaseManager):
        super().__init__()
        self.sio_manager = sio_manager

    # ---------------------------------------------------------------------------
    #   Events Aggregator -> Web workers -> Clients
    # ---------------------------------------------------------------------------
    async def on_weather_current(self, sid, data):
        logger.debug("Dispatching 'weather_current' to clients")
        await self.sio_manager.emit("weather_current", data=data, namespace="/")

    async def on_weather_hourly(self, sid, data):
        logger.debug("Dispatching 'weather_hourly' to clients")
        await self.sio_manager.emit("weather_hourly", data=data, namespace="/")

    async def on_weather_daily(self, sid, data):
        logger.debug("Dispatching 'weather_daily' to clients")
        await self.sio_manager.emit("weather_daily", data=data, namespace="/")

    async def on_sun_times(self, sid, data):
        logger.debug("Dispatching 'sun_times' to clients")
        await self.sio_manager.emit("sun_times", data=data, namespace="/")

    async def on_ecosystem_status(self, sid, data):
        logger.debug("Dispatching 'ecosystem_status' to clients")
        await self.sio_manager.emit("ecosystem_status", data=data, namespace="/")

    async def on_current_sensors_data(self, sid, data):
        logger.debug("Dispatching 'current_sensors_data' to clients")
        await self.sio_manager.emit("current_sensors_data", data=data, namespace="/")

    async def on_light_data(self, sid, data):
        logger.debug("Dispatching 'light_data' to clients")
        await self.sio_manager.emit("light_data", data=data, namespace="/")

    async def on_actuator_data(self, sid, data):
        logger.debug("Dispatching 'light_data' to clients")
        await self.sio_manager.emit("actuator_data", data=data, namespace="/")

    # ---------------------------------------------------------------------------
    #   Events Root Web server ->  Web workers -> Clients
    # ---------------------------------------------------------------------------
    async def on_current_server_data(self, sid, data):
        logger.debug("Dispatching 'current_server_data' to clients")
        await self.sio_manager.emit("current_server_data", data=data, namespace="/")
