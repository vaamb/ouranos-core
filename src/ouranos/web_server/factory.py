from __future__ import annotations

import logging
import time as ctime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import APIRouter, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from socketio.asgi import ASGIApp
from socketio.asyncio_server import AsyncServer

from .docs import description, tags_metadata
from ouranos import current_app
from ouranos.core.utils import (
    check_secret_key, DispatcherFactory, stripped_warning
)

try:
    import orjson
except ImportError:
    try:
        import ujson
    except ImportError:
        from fastapi.responses import JSONResponse
    else:
        from fastapi.responses import UJSONResponse as JSONResponse
else:
    from fastapi.responses import ORJSONResponse as JSONResponse


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


dispatcher = DispatcherFactory.get("application")
sio_manager = create_sio_manager()
sio = AsyncServer(
    async_mode='asgi', cors_allowed_origins=[], client_manager=sio_manager
)
asgi_app = ASGIApp(sio)


def create_app(config: dict | None = None) -> FastAPI:
    config = config or current_app.config
    if not config:
        raise RuntimeError(
            "Either provide a config dict or set config globally with "
            "g.set_app_config"
        )
    check_secret_key(config)
    logger = logging.getLogger("ouranos.web_server")
    logger.debug("Initializing FastAPI application")

    app = FastAPI(
        title=config.get("APP_NAME"),
        version=config.get("VERSION"),
        description=description,
        openapi_tags=tags_metadata,
        docs_url="/web_server/docs",
        redoc_url="/web_server/redoc",
        default_response_class=JSONResponse,
    )

    app.extra["logger"] = logger

    if config.get("DEVELOPMENT") or config.get("TESTING"):
        allowed_origins = ("http://127.0.0.1:8080", "http://localhost:8080")
    else:
        allowed_origins = ()

    # Set up CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
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

    @app.on_event("startup")
    def startup():
        logger.info("Ouranos web server worker successfully started")
        dispatcher.start()

    # Add a router with "/web_server" path prefixed to it
    prefix = APIRouter(prefix="/api")

    # Load routes onto prefixed router
    logger.debug("Loading app-related routes")
    from .routes.app import router as app_router
    app_router.default_response_class = JSONResponse
    prefix.include_router(app_router)

    logger.debug("Loading auth-related routes")
    from .routes.auth import router as auth_router
    app_router.default_response_class = JSONResponse
    prefix.include_router(auth_router)

    logger.debug("Loading gaia-related routes")
    from .routes.gaia import router as gaia_router
    gaia_router.default_response_class = JSONResponse
    prefix.include_router(gaia_router)

    logger.debug("Loading system-related routes")
    from .routes.system import router as system_router
    system_router.default_response_class = JSONResponse
    prefix.include_router(system_router)

    logger.debug("Loading weather-related routes")
    from .routes.weather import router as weather_router
    weather_router.default_response_class = JSONResponse
    prefix.include_router(weather_router)

    # Load prefixed routes
    app.include_router(prefix)

    # Teapots should not brew coffee
    @app.get("/coffee", include_in_schema=False)
    async def get_coffee():
        raise HTTPException(
            status_code=status.HTTP_418_IM_A_TEAPOT,
            detail="I'm a teapot, I can't brew coffee"
        )
    logger.debug("Brewing coffee???")

    # Configure Socket.IO and load the socketio
    logger.debug("Configuring Socket.IO server")
    app.mount(path="/", app=asgi_app)

    logger.debug("Loading client events")
    from ouranos.web_server.events import ClientEvents, DispatcherEvents
    # Events coming from client through sio, to dispatch to Ouranos
    namespace = ClientEvents("/")
    namespace.ouranos_dispatcher = dispatcher
    sio.register_namespace(namespace)
    # Events coming from Ouranos dispatcher, to send to client through sio
    event_handler = DispatcherEvents("application")
    dispatcher.register_event_handler(event_handler)

    # Load the frontend if present
    frontend_static_dir = current_app.base_dir/"frontend/dist"
    frontend_index = frontend_static_dir/"index.html"
    if frontend_index.exists():
        logger.debug("Ouranos frontend detected, mounting it")
        app.mount("/", StaticFiles(directory=frontend_static_dir, html=True))

    logger.info(f"{config['APP_NAME']} web server successfully created")
    return app


"""
def create_app(config_class=DevelopmentConfig):
    logger.debug("Adding wiki static folder")
    # from ouranos.app.wiki.routing import bp as wiki_bp
    # app.register_blueprint(wiki_bp)
"""