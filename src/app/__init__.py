from fastapi import APIRouter, FastAPI, HTTPException, status

from src.app.docs import tags_metadata
from src.database.wrapper import SQLAlchemyWrapper
from src.utils import config_dict_from_class
from config import Config

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


db = SQLAlchemyWrapper()


def create_app(config) -> FastAPI:
    config_dict = config_dict_from_class(Config)

    global app_config
    app_config = config_dict

    app = FastAPI(
        title=config_dict.get("APP_NAME"),
        version=config_dict.get("VERSION"),
        openapi_tags=tags_metadata,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        default_response_class=JSONResponse
    )
    # Init db
    from src.database.models import app as app_models, archives, gaia, system
    db.init(config)
    db.create_all()
    app.db = db

    # Add a router with "/api" path prefixed to it
    prefix = APIRouter(prefix="/api")

    # Load routes onto prefixed router
    from .routes.app import router as app_router
    app_router.default_response_class = JSONResponse
    prefix.include_router(app_router)

    from .routes.auth import router as auth_router
    app_router.default_response_class = JSONResponse
    prefix.include_router(auth_router)

    from .routes.system import router as system_router
    system_router.default_response_class = JSONResponse
    prefix.include_router(system_router)

    from .routes.weather import router as weather_router
    app_router.default_response_class = JSONResponse
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
    return app


app = create_app(Config)


"""import logging
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from dispatcher import configure_dispatcher
from flask import Flask
from flask_cors import CORS
from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO

from config import Config, DevelopmentConfig
from src.database.models import base
from src.database.models.app import CommunicationChannel, Role, User
from src.utils import json, JSONEncoder


app_name = Config.APP_NAME
app_path = Path(__file__).absolute().parents[0]

logger = logging.getLogger(f"{app_name.lower()}.app")

scheduler = BackgroundScheduler()

db = SQLAlchemy(model_class=base)
#jwtManager = JWTManager()
login_manager = LoginManager()
#mail = Mail()
#migrate = Migrate()
sio = SocketIO(json=json, cors_allowed_origins="*")
cors = CORS()


def create_app(config_class=DevelopmentConfig):
    if not any((config_class.DEBUG, config_class.TESTING)):
        for secret in ("SECRET_KEY", "JWT_SECRET_KEY", "GAIA_SECRET_KEY"):
            if vars(config_class)[secret] == \
                    "BXhNmCEmNdoBNngyGXj6jJtooYAcKpt6":
                raise Exception(
                    f"You need to set the environment variable '{secret}' when "
                    f"using gaiaWeb in a production environment."
                )

    logger.info(f"Creating {app_name} app ...")
    app = Flask(app_name, root_path=str(app_path))

    app.config.from_object(config_class)
    app.jinja_env.lstrip_blocks = True
    app.jinja_env.trim_blocks = True
    app.json_encoder = JSONEncoder

    configure_dispatcher(config_class, silent=True)

    # Init db
    db.init_app(app)
    with app.app_context():
        try:
            db.create_all()
            Role.insert_roles(db)
            User.insert_gaia(db)
            CommunicationChannel.insert_channels(db)
        except Exception as e:
            logger.error(e)

    # TODO: fine tune
    CORS(
        app,
        resources={
            r"/api/*": {
                "origins": ["http://127.0.0.1:8080", "http://localhost:8080"],
            },
        },
        supports_credentials=True,
    )

    #jwtManager.init_app(app)
    login_manager.init_app(app)  # TODO: look at add_context_processor=False
    #mail.init_app(app)
    #migrate.init_app(app, db)

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

    logger.debug("Loading api blueprint")
    from src.app.routes import bp as api_bp
    app.register_blueprint(api_bp)

    logger.debug("Loading events")
    from src.app import events
    from src.app.events.shared_resources import dispatcher
    dispatcher.start()

    logger.info(f"{app_name} app successfully created")

    return app
"""