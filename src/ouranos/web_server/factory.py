from __future__ import annotations

from contextlib import asynccontextmanager
import logging
import time as ctime
from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse as BaseResponse
from fastapi.staticfiles import StaticFiles
from socketio import AsyncManager, AsyncServer
from socketio.asgi import ASGIApp

from ouranos import current_app
from ouranos.core.dispatchers import DispatcherFactory
from ouranos.core.plugins_manager import PluginManager
from ouranos.core.utils import check_secret_key, json
from ouranos.web_server.docs import description, tags_metadata


class JSONResponse(BaseResponse):
    # Customize based on fastapi.responses.ORJSONResponse

    media_type = "application/json"

    def render(self, content: Any) -> bytes:
        return json.dumps(content)


def create_sio_manager(config: dict | None = None):
    config = config or current_app.config
    if not config:
        raise RuntimeError(
            "Either provide a config dict or set config globally with "
            "g.set_app_config"
        )
    sio_manager_url = config["SIO_MANAGER_URL"]
    if sio_manager_url.startswith("memory://"):
        from socketio import AsyncManager
        return AsyncManager()
    elif sio_manager_url.startswith("redis://"):
        from socketio import AsyncRedisManager
        uri = sio_manager_url.removeprefix("redis://")
        if not uri:
            uri = "localhost:6379/0"
        url = f"redis://{uri}"
        return AsyncRedisManager(url)
    elif sio_manager_url.startswith("amqp://"):
        from socketio import AsyncAioPikaManager
        uri = sio_manager_url.removeprefix("amqp://")
        if not uri:
            uri = "guest:guest@localhost:5672//"
        url = f"redis://{uri}"
        return AsyncAioPikaManager(url)
    else:
        raise RuntimeError(
            "'SIO_MANAGER_URL' is not set to a supported protocol, choose"
            "from 'memory', 'redis' or 'amqp'"
        )


def create_app(config: dict | None = None) -> FastAPI:
    config = config or current_app.config
    if not config:
        raise RuntimeError(
            "Either provide a config dict or set config globally with "
            "g.set_app_config"
        )
    logger = logging.getLogger("ouranos.web_server")
    secret = check_secret_key(config)
    if secret is not None:
        logger.warning(secret)
    logger.debug("Initializing FastAPI application")

    app = FastAPI(
        title=config.get("APP_NAME"),
        version=config.get("VERSION"),
        description=description,
        openapi_tags=tags_metadata,
        openapi_url="/api/openapi.json",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        default_response_class=JSONResponse,
    )

    # Set up CORS
    allowed_origins = []
    allowed_origins_regex = None

    if config.get("DEVELOPMENT") or config.get("TESTING"):
        allowed_origins += [
            "http://127.0.0.1:5173", "ws://127.0.0.1:5173",  # Vite development server
            "http://localhost:5173", "ws://localhost:5173",
            "http://127.0.0.1:3000", "ws://127.0.0.1:3000",  # Node server
            "http://localhost:3000", "ws://localhost:3000",
        ]

    if config.get("ALLOWED_ORIGINS"):
        origins = config["ALLOWED_ORIGINS"].split(",")
        allowed_origins += origins

    frontend_address = config.get("FRONTEND_ADDRESS")
    frontend_port = config.get("FRONTEND_PORT")
    if frontend_address and frontend_port:
        use_ssl = config.get("FRONTEND_USE_SSL", False)
        s = "s" if use_ssl else ""
        allowed_origins_regex = f"((http{s})|(ws{s}))://{frontend_address}:{frontend_port}"

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        allow_origin_regex=allowed_origins_regex,
    )

    # Add processing (brewing) time in headers when developing and testing
    if config.get("DEVELOPMENT") or config.get("TESTING"):
        @app.middleware("http")
        async def add_brewing_time_header(request: Request, call_next):
            start_time = ctime.monotonic()
            response = await call_next(request)
            brewing_time = ctime.monotonic() - start_time
            response.headers["X-Brewing-Time"] = str(brewing_time)
            return response

    # Add a router with "/api" path prefixed to it
    prefix = APIRouter(prefix="/api")

    # Load routes onto prefixed router
    logger.debug("Loading app-related routes")
    from ouranos.web_server.routes.app import router as app_router
    app_router.default_response_class = JSONResponse
    prefix.include_router(app_router)

    logger.debug("Loading auth-related routes")
    from ouranos.web_server.routes.auth import router as auth_router
    auth_router.default_response_class = JSONResponse
    prefix.include_router(auth_router)

    logger.debug("Loading user-related routes")
    from ouranos.web_server.routes.user import router as user_router
    user_router.default_response_class = JSONResponse
    prefix.include_router(user_router)

    logger.debug("Loading gaia-related routes")
    from ouranos.web_server.routes.gaia import router as gaia_router
    gaia_router.default_response_class = JSONResponse
    prefix.include_router(gaia_router)

    logger.debug("Loading system-related routes")
    from ouranos.web_server.routes.system import router as system_router
    system_router.default_response_class = JSONResponse
    prefix.include_router(system_router)

    logger.debug("Loading services-related routes")
    from ouranos.web_server.routes.services import router as services_router
    services_router.default_response_class = JSONResponse
    prefix.include_router(services_router)

    if current_app.config["TESTING"]:
        logger.debug("Loading tests-related routes")
        from ouranos.web_server.routes.tests import router as tests_router
        tests_router.default_response_class = JSONResponse
        prefix.include_router(tests_router)

    # Load add-on routes onto api router with "/addons"
    logger.debug("Loading add-on routes")
    addon_routes = APIRouter(prefix="/addons")
    pm = PluginManager()
    pm.register_plugins()
    pm.register_plugins_routes(addon_routes, JSONResponse)
    prefix.include_router(addon_routes)

    # Load prefixed routes
    app.include_router(prefix)

    # Teapots should not brew coffee
    logger.debug("- Brewing coffee???")

    @app.get("/coffee", include_in_schema=False)
    async def get_coffee():
        raise HTTPException(
            status_code=status.HTTP_418_IM_A_TEAPOT,
            detail="I'm a teapot, I can't brew coffee"
        )

    logger.debug("- I'd rather have tea")

    # Mount the static dir
    app.mount("/static", StaticFiles(directory=current_app.static_dir))

    # Configure Socket.IO and load the socketio
    logger.debug("Configuring Socket.IO server")
    dispatcher = DispatcherFactory.get("application-internal")
    sio_manager: AsyncManager = create_sio_manager()
    sio = AsyncServer(
        async_mode='asgi', cors_allowed_origins=[], client_manager=sio_manager)
    asgi_app = ASGIApp(sio)
    app.mount(path="/", app=asgi_app)

    logger.debug("Loading client events")
    from ouranos.web_server.events import ClientEvents, DispatcherEvents
    # Events coming from client through sio, to dispatch to Ouranos
    namespace = ClientEvents()
    namespace.ouranos_dispatcher = dispatcher
    sio.register_namespace(namespace)
    # Events coming from Ouranos dispatcher, to send to client through sio
    event_handler = DispatcherEvents(sio_manager)
    dispatcher.register_event_handler(event_handler)

    @asynccontextmanager
    async def lifespan(app_: FastAPI):
        logger.info("Ouranos web server worker successfully started")
        await dispatcher.start(retry=True, block=False)
        yield
        await dispatcher.stop()

    app.router.lifespan_context = lifespan

    return app

"""
def create_app(config_class=DevelopmentConfig):
    logger.debug("Adding wiki static folder")
    # from ouranos.app.wiki.routing import bp as wiki_bp
    # app.register_blueprint(wiki_bp)
"""
