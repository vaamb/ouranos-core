import asyncio
from logging import getLogger, Logger
from pathlib import Path
from typing import Any

from anyio.to_thread import run_sync
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route
from starlette import status
from uvicorn import Config, Server

from gaia_validators.image import SerializableImage

from ouranos import current_app, db
from ouranos.core.config.consts import TOKEN_SUBS
from ouranos.core.database.models.gaia import Ecosystem, Hardware
from ouranos.core.exceptions import TokenError
from ouranos.core.utils import json, Tokenizer


class JSONResponse(Response):
    # Customize based on fastapi.responses.ORJSONResponse

    media_type = "application/json"

    def render(self, content: Any) -> bytes:
        return json.dumps(content)


class FileServer:
    def __init__(self):
        self.logger: Logger = getLogger("ouranos.aggregator.server")
        self.static_dir = current_app.static_dir
        self._image_max_size = 4 * 1024 * 1024
        self.app = Starlette(routes=self.routes)
        host: str = current_app.config.get("AGGREGATOR_HOST", "127.0.0.1")
        port: int = current_app.config.get("AGGREGATOR_PORT", 7191)
        server_cfg = Config(
            app=self.app, host=host, port=port, log_config=None,
            server_header=False, date_header=False)
        self.server = Server(config=server_cfg)
        self._future = None

    """Start stop logic"""
    @property
    def started(self) -> bool:
        return self._future is not None

    async def start(self):
        if self.started:
            raise Exception("Server already started")
        self.logger.info("Starting the file server")
        self._future = asyncio.ensure_future(self.server.serve())
        host = self.server.config.host
        port = self.server.config.port
        self.logger.info(f"Server started at http://{host}:{port}.")

    async def stop(self):
        if not self.started:
            raise Exception("Server not started")
        self.logger.info("Stopping the file server")
        self.server.should_exit = True
        await self._future

    """Starlette app logic"""
    @property
    def routes(self) -> list[Route]:
        return [
            Route("/upload_camera_image", self.upload_camera_image, methods=["POST"]),
        ]

    async def upload_camera_image(self, request: Request):
        # Check we have a valid token
        token = request.headers.get("token")
        try:
            claims = Tokenizer.loads(token)
            if not claims.get("sub") == TOKEN_SUBS.CAMERA_UPLOAD.value:
                raise TokenError
        except TokenError:
            return JSONResponse(
                content={"detail": "Invalid token"},
                status_code=status.HTTP_401_UNAUTHORIZED
            )
        # Get the serialized image
        chunks = bytearray()
        async for chunk in request.stream():
            chunks.extend(chunk)
            if len(chunks) > self._image_max_size:
                return JSONResponse(
                    content={"detail": "Image too large"},
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
                )
        # Check that the ecosystem and camera are known
        image = SerializableImage.deserialize(chunks)
        ecosystem_uid = image.metadata["ecosystem_uid"]
        camera_uid = image.metadata["camera_uid"]
        async with db.scoped_session() as session:
            ecosystem = await Ecosystem.get(session, uid=ecosystem_uid)
            camera = await Hardware.get(session, uid=camera_uid)
            if ecosystem is None or camera is None:
                return JSONResponse(
                    content={"detail": "Unknown ecosystem or camera uid"},
                    status_code=status.HTTP_404_NOT_FOUND
                )
            if camera.ecosystem_uid != ecosystem.uid:
                return JSONResponse(
                    content={"detail": "Camera does not belong to ecosystem"},
                    status_code=status.HTTP_400_BAD_REQUEST
                )
        # Save the picture
        if image.is_compressed:
            image.uncompress(inplace=True)
        picture_name = f"{camera_uid}.jpeg"
        picture_path = self.static_dir / "camera_stream" / ecosystem_uid / picture_name
        await run_sync(self._write_image, image, picture_path)
        return JSONResponse(content={"detail": "Image uploaded"})

    @staticmethod
    def _write_image(image: SerializableImage, path: Path) -> None:
        if not path.parent.exists():
            path.parent.mkdir(parents=True)
        image.write(path)
