import asyncio
import logging
import time as ctime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dispatcher import configure_dispatcher, get_dispatcher
from fastapi import APIRouter, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from socketio import ASGIApp, AsyncManager, AsyncServer

from .docs import description, tags_metadata
from .utils import set_app_config
from src.core import db
from src.core.g import base_dir, set_base_dir
from src.core.utils import config_dict_from_class, Tokenizer

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


dispatcher = get_dispatcher(namespace="application")
scheduler = AsyncIOScheduler()
sio = AsyncServer(async_mode='asgi', cors_allowed_origins=[])
asgi_app = ASGIApp(sio)


def create_app(config) -> FastAPI:
    config_dict = config_dict_from_class(config)
    set_app_config(config_dict)
    from .utils import app_config

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

    # Init db
    from src.core.database.models import Role, User, CommunicationChannel
    db.init(config)

    async def create_base_data():
        async with db.scoped_session() as session:
            try:
                await Role.insert_roles(session)
                await User.insert_gaia(session)
                await CommunicationChannel.insert_channels(session)
            except Exception as e:
                logger.error(e)
                raise e

    loop = asyncio.get_event_loop()
    loop.create_task(db.create_all())
    loop.create_task(create_base_data())
    app.extra["db"] = db

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
    if 0 and app_config.get("USE_REDIS_DISPATCHER", False):
        sio.manager = AsyncManager()  # TODO
        sio.manager.set_server(sio)
    app.mount(path="/", app=asgi_app)

    logger.debug("Loading client events")
    from src.app.socketio import Events as ClientEvents
    sio.register_namespace(ClientEvents("/"))

    logger.debug("Loading gaia events")
    from src.core.connection.events import Events as GAIAEvents
    sio.register_namespace(GAIAEvents("/gaia"))

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