import asyncio
import logging
import time as ctime

from fastapi import APIRouter, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from socketio import AsyncServer, ASGIApp

from .docs import description, tags_metadata
from src.database.wrapper import AsyncSQLAlchemyWrapper
from src.utils import base_dir, config_dict_from_class, Tokenizer

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


app_config: dict[str, str] = {}


db = AsyncSQLAlchemyWrapper()
sio = AsyncServer(
    async_mode='asgi'
)


def create_app(config) -> FastAPI:
    config_dict = config_dict_from_class(config)

    if not any((config_dict.get("DEBUG"), config_dict.get("TESTING"))):
        for secret in ("SECRET_KEY", "JWT_SECRET_KEY", "GAIA_SECRET_KEY"):
            if config_dict.get(secret) == "BXhNmCEmNdoBNngyGXj6jJtooYAcKpt6":
                raise Exception(
                    f"You need to set the environment variable '{secret}' when "
                    f"using gaiaWeb in a production environment."
                )

    global app_config
    app_config = config_dict
    logger_name = config_dict['APP_NAME'].lower()
    logger = logging.getLogger(f"{logger_name}.app")
    logger.info(f"Creating {config_dict['APP_NAME']} app ...")

    Tokenizer.secret_key = app_config["SECRET_KEY"]

    app = FastAPI(
        title=config_dict.get("APP_NAME"),
        version=config_dict.get("VERSION"),
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
    if config_dict.get("DEBUG") or config_dict.get("TESTING"):
        @app.middleware("http")
        async def add_brewing_time_header(request: Request, call_next):
            start_time = ctime.monotonic()
            response = await call_next(request)
            brewing_time = ctime.monotonic() - start_time
            response.headers["X-Brewing-Time"] = str(brewing_time)
            return response

    @app.on_event("startup")
    def startup():
        logger.info(f"{config_dict['APP_NAME']} worker successfully started")

    # Init db
    from src.database.models import app as app_models, archives, gaia, system  # noqa # need import for sqlalchemy metadata generation
    db.init(config)

    async def create_base_data():
        async with db.scoped_session() as session:
            try:
                await app_models.Role.insert_roles(session)
                await app_models.User.insert_gaia(session)
                await app_models.CommunicationChannel.insert_channels(session)
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

    # Workaround so python-socketio doesn't add its own headers, which leads to CORS issues
    sio.eio.cors_allowed_origins = []
    sio_app = ASGIApp(socketio_server=sio)
    app.mount(path="/", app=sio_app)

    frontend_static_dir = base_dir/"frontend/dist"
    frontend_index = frontend_static_dir/"index.html"
    if frontend_index.exists():
        logger.debug("Ouranos frontend detected, mounting it")
        app.mount("/", StaticFiles(directory=frontend_static_dir, html=True))

    logger.info(f"{config_dict['APP_NAME']} app successfully created")
    return app


"""import logging
from apscheduler.schedulers.background import BackgroundScheduler
from dispatcher import configure_dispatcher
from flask_socketio import SocketIO


scheduler = BackgroundScheduler()

sio = SocketIO(json=json, cors_allowed_origins="*")

def create_app(config_class=DevelopmentConfig):

    configure_dispatcher(config_class, silent=True)

    # TODO: first check connection to server, and use Kombu instead
    if 0 and app.config["USE_REDIS_DISPATCHER"]:
        sio.init_app(app, message_queue=app.config["REDIS_URL"])
    else:
        sio.init_app(app)

    if config_class.__name__ != "TestingConfig":
        scheduler.start()

    logger.debug("Adding wiki static folder")
    # from src.app.wiki.routing import bp as wiki_bp
    # app.register_blueprint(wiki_bp)

    logger.debug("Loading events")
    from src.app import events
    from src.app.events.shared_resources import dispatcher
    dispatcher.start()

    return app
"""