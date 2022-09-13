from __future__ import annotations

import logging
import time as ctime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dispatcher import configure_dispatcher, get_dispatcher, AsyncDispatcher
from fastapi import APIRouter, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from socketio import ASGIApp, AsyncManager, AsyncServer

from .docs import description, tags_metadata
from src.core.g import base_dir, db, set_app_config, set_base_dir
from src.core.utils import config_dict_from_class, get_config, Tokenizer

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


dispatcher: AsyncDispatcher = get_dispatcher(namespace="application", async_based=True)
scheduler = AsyncIOScheduler()
sio = AsyncServer(async_mode='asgi', cors_allowed_origins=[])
sio_manager: AsyncManager = AsyncManager()
asgi_app = ASGIApp(sio)


def create_app(config_profile: str | None = None) -> FastAPI:
    try:
        config_class = get_config(config_profile)
    except ValueError:
        config_class = get_config("default")

    config_dict = config_dict_from_class(config_class)
    set_app_config(config_dict)
    from src.core.g import app_config
    if not any((app_config.get("DEBUG"), app_config.get("TESTING"))):
        for secret in ("SECRET_KEY", "JWT_SECRET_KEY", "GAIA_SECRET_KEY"):
            if app_config.get(secret) == "BXhNmCEmNdoBNngyGXj6jJtooYAcKpt6":
                raise Exception(
                    f"You need to set the environment variable '{secret}' when "
                    f"using gaiaWeb in a production environment."
                )

    if app_config.get("DIR"):
        set_base_dir(app_config["DIR"])

    logger_name = app_config['APP_NAME'].lower()
    logger = logging.getLogger(f"{logger_name}.app")
    logger.info(f"Creating {app_config['APP_NAME']} app ...")

    Tokenizer.secret_key = app_config["SECRET_KEY"]

    app = FastAPI(
        title=app_config.get("APP_NAME"),
        version=app_config.get("VERSION"),
        description=description,
        openapi_tags=tags_metadata,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        default_response_class=JSONResponse,
    )

    app.extra["logger"] = logger

    if app_config.get("TESTING"):
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

    # Add processing (brewing) time in headers when testing and debugging
    if app_config.get("DEBUG") or app_config.get("TESTING"):
        @app.middleware("http")
        async def add_brewing_time_header(request: Request, call_next):
            start_time = ctime.monotonic()
            response = await call_next(request)
            brewing_time = ctime.monotonic() - start_time
            response.headers["X-Brewing-Time"] = str(brewing_time)
            return response

    @app.on_event("startup")
    def startup():
        logger.info(f"{app_config['APP_NAME']} worker successfully started")

    # Add a router with "/api" path prefixed to it
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

    # Load event dispatcher and start it
    configure_dispatcher(app_config, silent=True)
    # dispatcher.start()

    # Start the background scheduler
    @app.on_event("startup")
    def start_scheduler():
        scheduler.start()

    # Configure Socket.IO and load the socketio
    logger.debug("Configuring Socket.IO server")
    global sio_manager
    message_broker_url = app_config.get("MESSAGE_BROKER_URL", "memory://")
    if message_broker_url.startswith("memory://"):
        pass
        # already using base AsyncManager
    elif message_broker_url.startswith("redis://"):
        from socketio import AsyncRedisManager
        uri = message_broker_url.removeprefix("redis://")
        if not uri:
            uri = "localhost:6379/0"
        url = f"redis://{uri}"
        sio_manager = AsyncRedisManager(url)
    elif message_broker_url.startswith("amqp://"):
        from socketio import AsyncAioPikaManager
        uri = message_broker_url.removeprefix("amqp://")
        if not uri:
            uri = "guest:guest@localhost:5672//"
        url = f"redis://{uri}"
        sio_manager = AsyncAioPikaManager(url)
    else:
        raise RuntimeError(
            "'MESSAGE_BROKER_URL' is not set to a supported protocol, choose"
            "from 'memory', 'redis' or 'amqp'"
        )
    sio.manager = sio_manager
    sio.manager.set_server(sio)
    app.mount(path="/", app=asgi_app)

    logger.debug("Loading client events")
    from src.app.socketio import Events as ClientEvents
    sio.register_namespace(ClientEvents("/"))

    logger.debug("Loading gaia events")
    gaia_broker_url = app_config.get("GAIA_BROKER_URL", "socketio://")
    if gaia_broker_url.startswith("socketio://"):
        from src.core.communication.socketio import GaiaEventsNamespace
        sio.register_namespace(GaiaEventsNamespace("/gaia"))
    else:
        from src.core.communication.dispatcher import GaiaEventsNamespace
        dispatcher.register_event_handler(GaiaEventsNamespace())

    # Load the frontend if present
    frontend_static_dir = base_dir/"frontend/dist"
    frontend_index = frontend_static_dir/"index.html"
    if frontend_index.exists():
        logger.debug("Ouranos frontend detected, mounting it")
        app.mount("/", StaticFiles(directory=frontend_static_dir, html=True))

    logger.info(f"{app_config['APP_NAME']} app successfully created")
    return app


"""
def create_app(config_class=DevelopmentConfig):
    logger.debug("Adding wiki static folder")
    # from src.app.wiki.routing import bp as wiki_bp
    # app.register_blueprint(wiki_bp)
"""