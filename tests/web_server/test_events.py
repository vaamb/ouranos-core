from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime, timezone

import pytest

from sqlalchemy_wrapper import AsyncSQLAlchemyWrapper

import gaia_validators as gv

from ouranos.core.database.models.app import User
from ouranos.web_server.auth import SessionInfo
from ouranos.web_server.events import ADMIN_ROOM, ClientEvents

from tests.class_fixtures import EcosystemAware, UsersAware
from tests.data.auth import admin, user
import tests.data.gaia as g_data
from tests.utils import MockAsyncDispatcher


SID = "client_sid"


class MockSioServer:
    """Minimal stand-in for `socketio.AsyncServer` used by `ClientEvents`.

    Records every `emit` call and tracks room membership per sid so tests can
    assert both what was sent to the client and which rooms it ended up in.
    `ClientEvents` reaches the server in two ways: directly (`self.server.emit`,
    `self.server.enter_room`, ...) and through the inherited
    `AsyncNamespace.emit`, which also delegates to `self.server.emit`.
    """

    def __init__(self):
        self.emit_store: deque[dict] = deque()
        self.rooms: dict[str, set[str]] = defaultdict(set)

    async def emit(self, event, data=None, to=None, room=None, skip_sid=None,
                   namespace=None, callback=None, ignore_queue=False):
        self.emit_store.append({
            "event": event,
            "data": data,
            "to": to,
            "room": room,
            "namespace": namespace,
        })

    async def enter_room(self, sid, room, namespace=None):
        self.rooms[sid].add(room)

    async def leave_room(self, sid, room, namespace=None):
        self.rooms[sid].discard(room)


def make_token(user_id: int) -> str:
    return SessionInfo(id="session_id", user_id=user_id, remember=True).to_token()


@pytest.fixture(scope="function")
def mock_server() -> MockSioServer:
    return MockSioServer()


@pytest.fixture(scope="function")
def ouranos_dispatcher() -> MockAsyncDispatcher:
    return MockAsyncDispatcher("application-internal")


@pytest.fixture(scope="function")
def client_events(
        mock_server: MockSioServer,
        ouranos_dispatcher: MockAsyncDispatcher,
) -> ClientEvents:
    events = ClientEvents()
    events.server = mock_server
    events.ouranos_dispatcher = ouranos_dispatcher
    return events


class TestClientEventsDispatcher:
    def test_ouranos_dispatcher_property(self):
        """Test the ouranos_dispatcher property and its setter.

        Verifies that:
        - Accessing the dispatcher before it is set raises a RuntimeError
        - The setter stores the dispatcher and the getter returns it
        """
        events = ClientEvents()
        with pytest.raises(RuntimeError):
            _ = events.ouranos_dispatcher

        dispatcher = MockAsyncDispatcher("application-internal")
        events.ouranos_dispatcher = dispatcher
        assert events.ouranos_dispatcher is dispatcher


@pytest.mark.asyncio
class TestClientEventsBasics:
    async def test_on_ping(
            self,
            client_events: ClientEvents,
            mock_server: MockSioServer,
    ):
        """Test the ping handler.

        Verifies that:
        - A 'pong' event is emitted back to the requesting sid
        """
        await client_events.on_ping(SID)

        assert len(mock_server.emit_store) == 1
        emitted = mock_server.emit_store[0]
        assert emitted["event"] == "pong"
        assert emitted["room"] == SID
        assert emitted["namespace"] == "/"


@pytest.mark.asyncio
class TestClientAuthEvents(UsersAware):
    async def test_on_login_admin(
            self,
            client_events: ClientEvents,
            mock_server: MockSioServer,
            db: AsyncSQLAlchemyWrapper,
    ):
        """Test the login handler for an administrator.

        Verifies that:
        - A valid token grants the admin the administrator room
        - A successful login acknowledgment is emitted
        """
        await client_events.on_login(SID, make_token(admin.id))

        assert ADMIN_ROOM in mock_server.rooms[SID]
        emitted = mock_server.emit_store[-1]
        assert emitted["event"] == "login_ack"
        assert emitted["data"]["result"] == gv.Result.success
        assert emitted["room"] == SID
        assert emitted["namespace"] == "/"

    async def test_on_login_non_admin(
            self,
            client_events: ClientEvents,
            mock_server: MockSioServer,
            db: AsyncSQLAlchemyWrapper,
    ):
        """Test the login handler for a regular user.

        Verifies that:
        - A valid token logs the user in successfully
        - A non-admin user is NOT added to the administrator room
        """
        await client_events.on_login(SID, make_token(user.id))

        assert ADMIN_ROOM not in mock_server.rooms[SID]
        emitted = mock_server.emit_store[-1]
        assert emitted["event"] == "login_ack"
        assert emitted["data"]["result"] == gv.Result.success

    async def test_on_login_invalid_token(
            self,
            client_events: ClientEvents,
            mock_server: MockSioServer,
            db: AsyncSQLAlchemyWrapper,
    ):
        """Test the login handler with an invalid session token.

        Verifies that:
        - The user is not added to the administrator room
        - A failure acknowledgment with the proper reason is emitted
        """
        await client_events.on_login(SID, "not-a-valid-token")

        assert ADMIN_ROOM not in mock_server.rooms[SID]
        emitted = mock_server.emit_store[-1]
        assert emitted["event"] == "login_ack"
        assert emitted["data"]["result"] == gv.Result.failure
        assert emitted["data"]["reason"] == "Invalid session token"

    async def test_on_logout(
            self,
            client_events: ClientEvents,
            mock_server: MockSioServer,
            db: AsyncSQLAlchemyWrapper,
    ):
        """Test the logout handler.

        Verifies that:
        - The client is removed from the administrator room
        - A successful logout acknowledgment is emitted
        """
        # Pretend the client is currently in the admin room
        mock_server.rooms[SID].add(ADMIN_ROOM)

        await client_events.on_logout(SID, make_token(admin.id))

        assert ADMIN_ROOM not in mock_server.rooms[SID]
        emitted = mock_server.emit_store[-1]
        assert emitted["event"] == "logout_ack"
        assert emitted["data"]["result"] == gv.Result.success

    async def test_on_user_heartbeat(
            self,
            client_events: ClientEvents,
            mock_server: MockSioServer,
            db: AsyncSQLAlchemyWrapper,
    ):
        """Test the user heartbeat handler with a valid token.

        Verifies that:
        - The user's last_seen timestamp is refreshed
        - A heartbeat acknowledgment is emitted back to the sid
        """
        old = datetime(2020, 1, 1, tzinfo=timezone.utc)
        async with db.scoped_session() as session:
            await User.update(session, user_id=user.id, values={"last_seen": old})

        await client_events.on_user_heartbeat(SID, make_token(user.id))

        emitted = mock_server.emit_store[-1]
        assert emitted["event"] == "user_heartbeat_ack"
        assert emitted["to"] == SID
        assert emitted["namespace"] == "/"

        async with db.scoped_session() as session:
            refreshed = await User.get(session, user_id=user.id)
        assert refreshed.last_seen > old

    async def test_on_user_heartbeat_invalid_token(
            self,
            client_events: ClientEvents,
            mock_server: MockSioServer,
            db: AsyncSQLAlchemyWrapper,
    ):
        """Test the user heartbeat handler with an invalid token.

        Verifies that:
        - No acknowledgment is emitted when the token cannot be decoded
        """
        await client_events.on_user_heartbeat(SID, "garbage")

        assert len(mock_server.emit_store) == 0


@pytest.mark.asyncio
class TestClientRoomEvents:
    async def test_on_join_room(
            self,
            client_events: ClientEvents,
            mock_server: MockSioServer,
    ):
        """Test joining a regular room.

        Verifies that:
        - The client is added to the requested room
        - A successful acknowledgment is emitted
        """
        await client_events.on_join_room(SID, "some_room")

        assert "some_room" in mock_server.rooms[SID]
        emitted = mock_server.emit_store[-1]
        assert emitted["event"] == "join_room_ack"
        assert emitted["data"]["result"] == gv.Result.success

    @pytest.mark.xfail(
        reason="BUG: on_join_room is missing a `return` after the admin-room "
               "guard, so the client is still added to the admin room and also "
               "receives a success acknowledgment.",
        strict=False,
    )
    async def test_on_join_admin_room_is_rejected(
            self,
            client_events: ClientEvents,
            mock_server: MockSioServer,
    ):
        """Test that the administrator room cannot be joined directly.

        Verifies that:
        - The client is NOT added to the administrator room
        - Only a single failure acknowledgment is emitted
        """
        await client_events.on_join_room(SID, ADMIN_ROOM)

        assert ADMIN_ROOM not in mock_server.rooms[SID]
        assert len(mock_server.emit_store) == 1
        emitted = mock_server.emit_store[0]
        assert emitted["event"] == "join_room_ack"
        assert emitted["data"]["result"] == gv.Result.failure

    async def test_on_leave_room(
            self,
            client_events: ClientEvents,
            mock_server: MockSioServer,
    ):
        """Test leaving a regular room.

        Verifies that:
        - The client is removed from the requested room
        - A successful acknowledgment is emitted
        """
        mock_server.rooms[SID].add("some_room")

        await client_events.on_leave_room(SID, "some_room")

        assert "some_room" not in mock_server.rooms[SID]
        emitted = mock_server.emit_store[-1]
        assert emitted["event"] == "leave_room_ack"
        assert emitted["data"]["result"] == gv.Result.success

    @pytest.mark.xfail(
        reason="BUG: on_leave_room is missing a `return` after the admin-room "
               "guard, so the client is still removed from the admin room and "
               "also receives a success acknowledgment.",
        strict=False,
    )
    async def test_on_leave_admin_room_is_rejected(
            self,
            client_events: ClientEvents,
            mock_server: MockSioServer,
    ):
        """Test that the administrator room cannot be left directly.

        Verifies that:
        - The client is NOT removed from the administrator room
        - Only a single failure acknowledgment is emitted
        """
        mock_server.rooms[SID].add(ADMIN_ROOM)

        await client_events.on_leave_room(SID, ADMIN_ROOM)

        assert ADMIN_ROOM in mock_server.rooms[SID]
        assert len(mock_server.emit_store) == 1
        emitted = mock_server.emit_store[0]
        assert emitted["event"] == "leave_room_ack"
        assert emitted["data"]["result"] == gv.Result.failure


@pytest.mark.asyncio
class TestClientEcosystemCommands(EcosystemAware):
    @pytest.mark.xfail(
        reason="BUG: on_turn_light uses a sync `with db.scoped_session()` on an "
               "async context manager; it should be `async with`.",
        strict=False,
    )
    async def test_on_turn_light(
            self,
            client_events: ClientEvents,
            ouranos_dispatcher: MockAsyncDispatcher,
            db: AsyncSQLAlchemyWrapper,
    ):
        """Test the turn_light command handler.

        Verifies that:
        - A 'turn_light' signal is dispatched to the ecosystem's engine
        - The payload carries the ecosystem, mode and countdown
        - The signal is sent on the aggregator-internal namespace
        """
        data = {
            "ecosystem": g_data.ecosystem_uid,
            "mode": "automatic",
            "countdown": 0,
        }
        await client_events.on_turn_light(SID, data)

        assert len(ouranos_dispatcher.emit_store) == 1
        emitted = ouranos_dispatcher.emit_store[0]
        assert emitted["event"] == "turn_light"
        assert emitted["data"]["ecosystem"] == g_data.ecosystem_uid
        assert emitted["data"]["mode"] == "automatic"
        assert emitted["data"]["countdown"] == 0
        assert emitted["namespace"] == "aggregator-internal"
        assert emitted["room"] == g_data.engine_sid

    @pytest.mark.xfail(
        reason="BUG: on_manage_ecosystem uses a sync `with db.scoped_session()` "
               "on an async context manager; it should be `async with`.",
        strict=False,
    )
    async def test_on_manage_ecosystem(
            self,
            client_events: ClientEvents,
            ouranos_dispatcher: MockAsyncDispatcher,
            db: AsyncSQLAlchemyWrapper,
    ):
        """Test the manage_ecosystem command handler.

        Verifies that:
        - A 'change_management' signal is dispatched to the ecosystem's engine
        - The payload carries the ecosystem, management and status
        - The signal is sent on the aggregator-internal namespace
        """
        data = {
            "ecosystem": g_data.ecosystem_uid,
            "management": "light",
            "status": True,
        }
        await client_events.on_manage_ecosystem(SID, data)

        assert len(ouranos_dispatcher.emit_store) == 1
        emitted = ouranos_dispatcher.emit_store[0]
        assert emitted["event"] == "change_management"
        assert emitted["data"]["ecosystem"] == g_data.ecosystem_uid
        assert emitted["data"]["management"] == "light"
        assert emitted["data"]["status"] is True
        assert emitted["namespace"] == "aggregator-internal"
        assert emitted["room"] == g_data.engine_sid
