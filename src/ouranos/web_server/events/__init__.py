from __future__ import annotations

from datetime import datetime, timezone
from logging import getLogger, Logger

from dispatcher import AsyncDispatcher, AsyncEventHandler
import gaia_validators as gv
from socketio import AsyncNamespace, AsyncManager

from ouranos import db
from ouranos.core.database.models.app import Permission, User
from ouranos.core.database.models.gaia import Ecosystem
from ouranos.core.exceptions import TokenError
from ouranos.web_server.auth import login_manager, SessionInfo
from ouranos.web_server.events.decorators import permission_required


ADMIN_ROOM = "administrator"
CAMERA_STREAM_ROOM = "camera_stream"

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

    async def on_login(self, sid, token: str):
        try:
            session_info = SessionInfo.from_token(token)
        except TokenError:
            logger.warning(f"Received invalid session token from sid '{sid}'")
            await self.emit(
                "login_ack",
                data={
                    "result": gv.Result.failure,
                    "reason": "Invalid session token"
                },
                namespace="/",
                room=sid
            )
        else:
            async with db.scoped_session() as session:
                user = await login_manager.get_user(session, session_info.user_id)
            if user.can(Permission.ADMIN):
                self.server.enter_room(sid, ADMIN_ROOM)
            await self.emit(
                "login_ack",
                data={"result": gv.Result.success},
                namespace="/",
                room=sid
            )

    async def on_logout(self, sid, token: str):
        self.server.leave_room(sid, ADMIN_ROOM)
        await self.emit(
            "logout_ack",
            data={"result": gv.Result.success},
            namespace="/",
            room=sid
        )

    async def on_user_heartbeat(self, sid, token: str):
        try:
            session_info = SessionInfo.from_token(token)
        except TokenError:
            logger.warning(f"Received invalid session token from sid '{sid}'")
        else:
            if session_info.user_id > 0:
                async with db.scoped_session() as session:
                    await User.update(
                        session,
                        user_id=session_info.user_id,
                        values={"last_seen": datetime.now(timezone.utc)}
                    )
                await self.emit(
                    "user_heartbeat_ack",
                    to=sid,
                    namespace="/",
                )

    async def on_join_room(self, sid, room_name: str) -> None:
        if room_name == ADMIN_ROOM:
            await self.emit(
                "join_room_ack",
                data={
                    "result": gv.Result.failure,
                    "reason": "Admin room can only be entered via `login` event."
                },
                namespace="/",
                room=sid
            )
        self.server.enter_room(sid, room_name)
        await self.emit(
            "join_room_ack",
            data={"result": gv.Result.success,},
            namespace="/",
            room=sid
        )

    async def on_leave_room(self, sid, room_name: str) -> None:
        if room_name == ADMIN_ROOM:
            await self.emit(
                "leave_room_ack",
                data={
                    "result": gv.Result.failure,
                    "reason": "Admin room can only be left via `login` event."
                },
                namespace="/",
                room=sid
            )
        self.server.leave_room(sid, room_name)
        await self.emit(
            "leave_room_ack",
            data={"result": gv.Result.success,},
            namespace="/",
            room=sid
        )

    # ---------------------------------------------------------------------------
    #   Events Web clients ->  Web server -> Aggregator
    # ---------------------------------------------------------------------------
    # @permission_required(Permission.OPERATE)
    async def on_turn_light(self, sid, data):
        ecosystem_uid = data["ecosystem"]
        with db.scoped_session() as session:
            ecosystem = await Ecosystem.get(session, uid=ecosystem_uid)
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
            namespace="aggregator-internal",
        )

    # @permission_required(Permission.OPERATE)
    async def on_manage_ecosystem(self, sid, data):
        ecosystem_uid = data["ecosystem"]
        with db.scoped_session() as session:
            ecosystem = await Ecosystem.get(session, uid=ecosystem_uid)
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
            namespace="aggregator-internal",
            room=ecosystem_sid
        )


class DispatcherEvents(AsyncEventHandler):
    def __init__(self, sio_manager: AsyncManager):
        super().__init__()
        self.sio_manager = sio_manager

    # ---------------------------------------------------------------------------
    #   Events Aggregator -> Web workers -> Web clients
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

    async def on_ecosystems_heartbeat(self, sid, data):
        logger.debug("Dispatching 'ecosystem_heartbeat' to clients")
        await self.sio_manager.emit("ecosystems_heartbeat", data=data, namespace="/")

    async def on_base_info(self, sid, data):
        logger.debug("Dispatching 'base_info' to clients")
        await self.sio_manager.emit("base_info", data=data, namespace="/")

    async def on_hardware(self, sid, data):
        logger.debug("Dispatching 'hardware' to clients")
        await self.sio_manager.emit("hardware", data=data, namespace="/")

    async def on_environmental_parameters(self, sid, data):
        logger.debug("Dispatching 'environmental_parameters' to clients")
        await self.sio_manager.emit("environmental_parameters", data=data, namespace="/")

    async def on_chaos_parameters(self, sid, data):
        logger.debug("Dispatching 'chaos_parameters' to clients")
        await self.sio_manager.emit("chaos_parameters", data=data, namespace="/")

    async def on_nycthemeral_info(self, sid, data):
        logger.debug("Dispatching 'nycthemeral_info' to clients")
        await self.sio_manager.emit("nycthemeral_info", data=data, namespace="/")

    async def on_ecosystem_status(self, sid, data):
        logger.debug("Dispatching 'ecosystem_status' to clients")
        await self.sio_manager.emit("ecosystem_status", data=data, namespace="/")

    async def on_current_sensors_data(self, sid, data):
        logger.debug("Dispatching 'current_sensors_data' to clients")
        await self.sio_manager.emit("current_sensors_data", data=data, namespace="/")

    async def on_historic_sensors_data_update(self, sid, data):
        logger.debug("Dispatching 'historic_sensors_data_update' to clients")
        await self.sio_manager.emit(
            "historic_sensors_data_update", data=data, namespace="/")

    async def on_light_data(self, sid, data):
        logger.debug("Dispatching 'light_data' to clients")
        await self.sio_manager.emit("light_data", data=data, namespace="/")

    async def on_actuators_data(self, sid, data):
        logger.debug("Dispatching 'actuator_data' to clients")
        await self.sio_manager.emit("actuators_data", data=data, namespace="/")

    async def on_management(self, sid, data: list[gv.ManagementConfigPayloadDict]):
        logger.debug("Dispatching 'management' to clients")

        rv = []
        async with db.scoped_session() as session:
            for payload in data:
                payload_data = payload["data"]
                uid: str = payload["uid"]
                # Add extra functionalities required
                payload_data["switches"] = payload_data["climate"] or payload_data["light"]
                payload_data["environment_data"] = \
                    await Ecosystem.check_if_recent_sensor_data(
                        session, uid=uid, level=gv.HardwareLevel.environment)
                payload_data["plants_data"] = \
                    await Ecosystem.check_if_recent_sensor_data(
                        session, uid=uid, level=gv.HardwareLevel.plants)
                rv.append({
                    "uid": uid,
                    "data": payload_data,
                })
        await self.sio_manager.emit("management", data=rv, namespace="/")

    async def on_health_data(self, sid, data):
        logger.debug("Dispatching 'health_data' to clients")
        await self.sio_manager.emit("health_data", data=data, namespace="/")

    # ---------------------------------------------------------------------------
    #   Events Stream aggregator -> Web workers -> Web clients
    # ---------------------------------------------------------------------------
    async def on_picture_arrays(self, sid, data: dict) -> None:
        logger.debug("Dispatching picture updated to clients")
        await self.sio_manager.emit(
            "pictures_update", data=data, namespace="/", room=CAMERA_STREAM_ROOM)

    # ---------------------------------------------------------------------------
    #   Events Base web server ->  Web workers -> Admin web clients
    # ---------------------------------------------------------------------------
    async def on_current_server_data(self, sid, data):
        logger.debug("Dispatching 'current_server_data' to clients")
        await self.sio_manager.emit(
            "current_server_data", data=data, namespace="/", room=ADMIN_ROOM)
