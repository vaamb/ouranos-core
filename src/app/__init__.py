import logging
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from dispatcher import configure_dispatcher
from flask import Flask
from flask_cors import CORS
#from flask_jwt_extended import JWTManager
from flask_login import LoginManager
#from flask_mail import Mail
#from flask_migrate import Migrate
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
    from src.app.wiki.routing import bp as wiki_bp
    app.register_blueprint(wiki_bp)

    logger.debug("Loading api blueprint")
    from src.app.routes import bp as api_bp
    app.register_blueprint(api_bp)

    logger.debug("Loading events")
    from src.app import events
    from src.app.events.shared_resources import dispatcher
    dispatcher.start()

    logger.info(f"{app_name} app successfully created")

    return app
