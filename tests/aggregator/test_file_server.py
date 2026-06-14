from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest
from sqlalchemy.exc import IntegrityError
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient
from uvicorn import Server

from gaia_validators.image import SerializableImage, SerializableImagePayload
from sqlalchemy_wrapper import AsyncSQLAlchemyWrapper

from ouranos import current_app
from ouranos.aggregator.file_server import FileServer
from ouranos.core.config.consts import TOKEN_SUBS
from ouranos.core.database.models.gaia import CameraPicture
from ouranos.core.dispatchers import DispatcherFactory
from ouranos.core.utils import Tokenizer

from tests.class_fixtures import HardwareAware
import tests.data.gaia as g_data
from tests.utils import MockAsyncDispatcher


@pytest.fixture(scope="module")
def mock_internal_dispatcher():
    dispatcher = MockAsyncDispatcher("aggregator-internal")
    DispatcherFactory._DispatcherFactory__dispatchers["aggregator-internal"] = dispatcher
    yield dispatcher
    del DispatcherFactory._DispatcherFactory__dispatchers["aggregator-internal"]


@pytest.fixture(scope="function")
def file_server(mock_internal_dispatcher: MockAsyncDispatcher) -> FileServer:
    mock_internal_dispatcher.clear_store()
    return FileServer()


@pytest.fixture(scope="function")
def client(file_server: FileServer) -> TestClient:
    return TestClient(file_server.app)


def camera_token() -> str:
    return Tokenizer.dumps({"sub": TOKEN_SUBS.CAMERA_UPLOAD.value})


def make_image(
        *,
        camera_uid: str = g_data.camera_config["uid"],
        ecosystem_uid: str = g_data.ecosystem_uid,
        timestamp: datetime | None = None,
) -> SerializableImage:
    timestamp = timestamp or datetime.now(timezone.utc)
    array = np.zeros((2, 2, 3), dtype=np.uint8)
    return SerializableImage(
        array=array,
        metadata={
            "ecosystem_uid": ecosystem_uid,
            "camera_uid": camera_uid,
            "timestamp": timestamp.isoformat(),
            "extra": "value",
        },
    )


class TestFileServerInit:
    def test_init(self, file_server: FileServer):
        """Test the initialization and default attributes of a FileServer."""
        assert file_server._image_max_size == 1 * 1024 * 1024
        # The default config uses "both" as transfer method, so the server is needed
        assert file_server._server_needed is True
        assert file_server._app is None
        assert file_server._server is None
        assert file_server._future is None
        assert file_server.started is False
        assert file_server.camera_dir == Path(current_app.static_dir) / "camera_stream"

    def test_app_property(self, file_server: FileServer):
        """Test that the Starlette app is lazily built, cached and has the routes."""
        app = file_server.app
        assert isinstance(app, Starlette)
        # The property is cached
        assert file_server.app is app

        routes = file_server.routes
        assert all(isinstance(route, Route) for route in routes)
        paths = {route.path for route in routes}
        assert paths == {"/upload_camera_image", "/upload_camera_images"}

    def test_server_property(self, file_server: FileServer):
        """Test that the uvicorn server is lazily built, cached and configured."""
        server = file_server.server
        assert isinstance(server, Server)
        # The property is cached
        assert file_server.server is server
        assert server.config.host == current_app.config["AGGREGATOR_HOST"]
        assert server.config.port == current_app.config["AGGREGATOR_PORT"]


@pytest.mark.asyncio
class TestFileServerLifecycle:
    async def test_start_stop(self, file_server: FileServer):
        """Test the start/stop lifecycle of a needed file server."""
        assert file_server.started is False

        # Cannot stop a server that has not been started
        with pytest.raises(Exception):
            await file_server.stop()

        await file_server.start()
        assert file_server.started is True

        # Wait for uvicorn to complete its startup before stopping
        deadline = time.monotonic() + 5
        while not file_server.server.started:
            assert time.monotonic() < deadline, "The file server did not start in time"
            await asyncio.sleep(0.05)

        # Cannot start a server that is already started
        with pytest.raises(Exception):
            await file_server.start()

        await file_server.stop()
        assert file_server.server.should_exit is True

    async def test_start_not_needed(self, file_server: FileServer):
        """Test that starting a non-needed file server is a no-op."""
        file_server._server_needed = False
        await file_server.start()
        # The server was not actually started
        assert file_server.started is False


@pytest.mark.asyncio
class TestUploadCameraImage(HardwareAware):
    async def test_upload_camera_image(
            self,
            mock_internal_dispatcher: MockAsyncDispatcher,
            file_server: FileServer,
            client: TestClient,
            db: AsyncSQLAlchemyWrapper,
    ):
        """Test a successful single image upload."""
        timestamp = datetime.now(timezone.utc)
        image = make_image(timestamp=timestamp)

        response = client.post(
            "/upload_camera_image",
            content=bytes(image.serialize()),
            headers={"token": camera_token()},
        )

        assert response.status_code == 200
        assert response.json() == {"detail": "Image uploaded"}

        # Verify the image has been written to disk
        camera_uid = g_data.camera_config["uid"]
        rel_path = f"camera_stream/{g_data.ecosystem_uid}/{camera_uid}.jpeg"
        abs_path = Path(current_app.static_dir) / rel_path
        assert abs_path.exists()

        # Verify the metadata has been logged
        async with db.scoped_session() as session:
            picture = await CameraPicture.get(
                session,
                ecosystem_uid=g_data.ecosystem_uid,
                camera_uid=camera_uid,
            )
            assert picture is not None
            assert picture.path == rel_path
            assert picture.dimension == [2, 2, 3]
            assert picture.depth == "uint8"
            assert picture.timestamp == timestamp
            # The popped keys are gone, the rest of the metadata is kept
            assert picture.other_metadata == {"extra": "value"}

        # Verify the event has been dispatched
        assert len(mock_internal_dispatcher.emit_store) == 1
        emitted = mock_internal_dispatcher.emit_store[0]
        assert emitted["event"] == "picture_arrays"
        assert emitted["data"]["ecosystem_uid"] == g_data.ecosystem_uid
        updated_pictures = emitted["data"]["updated_pictures"]
        assert len(updated_pictures) == 1
        assert updated_pictures[0]["camera_uid"] == camera_uid
        assert updated_pictures[0]["path"] == rel_path
        assert updated_pictures[0]["timestamp"] == timestamp

    async def test_process_image(
            self,
            file_server: FileServer,
            db: AsyncSQLAlchemyWrapper,
    ):
        """Test that processing an image saves it and returns its info."""
        timestamp = datetime.now(timezone.utc)
        image = make_image(timestamp=timestamp)

        updated_picture = await file_server._process_image(image)

        camera_uid = g_data.camera_config["uid"]
        rel_path = f"camera_stream/{g_data.ecosystem_uid}/{camera_uid}.jpeg"
        assert updated_picture == {
            "camera_uid": camera_uid,
            "path": rel_path,
            "timestamp": timestamp,
        }
        assert (Path(current_app.static_dir) / rel_path).exists()

    def test_write_image_creates_directory(self, file_server: FileServer, tmp_path: Path):
        """Test that the image writing helper creates missing parent directories."""
        image = make_image()
        path = tmp_path / "missing" / "subdir" / "image.jpeg"
        assert not path.parent.exists()

        file_server._write_image(image, path)

        assert path.exists()

    async def test_upload_camera_image_no_token(self, client: TestClient):
        """Test that a missing token is rejected."""
        image = make_image()
        response = client.post(
            "/upload_camera_image",
            content=bytes(image.serialize()),
        )
        assert response.status_code == 401

    async def test_upload_camera_image_invalid_token(self, client: TestClient):
        """Test that a token with the wrong subject is rejected."""
        wrong_token = Tokenizer.dumps({"sub": "wrong_subject"})
        image = make_image()
        response = client.post(
            "/upload_camera_image",
            content=bytes(image.serialize()),
            headers={"token": wrong_token},
        )
        assert response.status_code == 401

    async def test_upload_camera_image_too_large(
            self,
            file_server: FileServer,
            client: TestClient,
    ):
        """Test that an oversized image is rejected with a 413."""
        file_server._image_max_size = 10
        response = client.post(
            "/upload_camera_image",
            content=b"a" * 100,
            headers={"token": camera_token()},
        )
        assert response.status_code == 413
        assert response.json() == {"detail": "Image too large"}

    async def test_upload_camera_image_unknown(self, client: TestClient):
        """Test that an unknown ecosystem or camera is rejected with a 400."""
        image = make_image()
        with patch.object(
                CameraPicture, "update_or_create", side_effect=IntegrityError("", "", Exception()),
        ):
            response = client.post(
                "/upload_camera_image",
                content=bytes(image.serialize()),
                headers={"token": camera_token()},
            )
        assert response.status_code == 400


@pytest.mark.asyncio
class TestUploadCameraImages(HardwareAware):
    async def test_upload_camera_images(
            self,
            mock_internal_dispatcher: MockAsyncDispatcher,
            client: TestClient,
            db: AsyncSQLAlchemyWrapper,
    ):
        """Test a successful multi-image upload."""
        timestamp = datetime.now(timezone.utc)
        image = make_image(timestamp=timestamp)
        payload = SerializableImagePayload(uid=g_data.ecosystem_uid, data=[image])

        response = client.post(
            "/upload_camera_images",
            content=bytes(payload.serialize()),
            headers={"token": camera_token()},
        )

        assert response.status_code == 200
        assert response.json() == {"detail": "Images uploaded"}

        # Verify the metadata has been logged
        camera_uid = g_data.camera_config["uid"]
        async with db.scoped_session() as session:
            picture = await CameraPicture.get(
                session,
                ecosystem_uid=g_data.ecosystem_uid,
                camera_uid=camera_uid,
            )
            assert picture is not None

        # Verify the event has been dispatched
        assert len(mock_internal_dispatcher.emit_store) == 1
        emitted = mock_internal_dispatcher.emit_store[0]
        assert emitted["event"] == "picture_arrays"
        assert emitted["data"]["ecosystem_uid"] == g_data.ecosystem_uid
        assert len(emitted["data"]["updated_pictures"]) == 1

    async def test_upload_camera_images_no_token(self, client: TestClient):
        """Test that a missing token is rejected."""
        image = make_image()
        payload = SerializableImagePayload(uid=g_data.ecosystem_uid, data=[image])
        response = client.post(
            "/upload_camera_images",
            content=bytes(payload.serialize()),
        )
        assert response.status_code == 401

    async def test_upload_camera_images_too_large(
            self,
            file_server: FileServer,
            client: TestClient,
    ):
        """Test that an oversized payload is rejected with a 413."""
        file_server._image_max_size = 10
        response = client.post(
            "/upload_camera_images",
            content=b"a" * 100,
            headers={"token": camera_token()},
        )
        assert response.status_code == 413
        assert response.json() == {"detail": "Images too large"}
