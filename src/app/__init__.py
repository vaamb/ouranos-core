import logging
from datetime import datetime, timezone
from pathlib import Path
import time

from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask, g
from flask_login import LoginManager
from flask_mail import Mail
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO

from config import Config, DevelopmentConfig
from src.models import Base, CommunicationChannel, Role, User
from src.utils import json, JSONEncoder


START_TIME = datetime.now(timezone.utc)

app_name = Config.APP_NAME
app_path = Path(__file__).absolute().parents[0]

logger = logging.getLogger(app_name)


scheduler = BackgroundScheduler()
login_manager = LoginManager()
db = SQLAlchemy(model_class=Base)
migrate = Migrate()
sio = SocketIO(json=json)
mail = Mail()


def create_app(config_class=DevelopmentConfig):
    if not any((config_class.DEBUG, config_class.TESTING)):
        for secret in ("SECRET_KEY", "JWT_SECRET_KEY", "GAIA_SECRET_KEY"):
            if vars(config_class)[secret] == "BXhNmCEmNdoBNngyGXj6jJtooYAcKpt6":
                raise Exception("You need to set the environment variable "
                                f"'{secret}' when using gaiaWeb in a "
                                "production environment.")

    logger.info(f"Creating {app_name} app ...")
    app = Flask(app_name, root_path=app_path)

    app.config.from_object(config_class)
    app.jinja_env.lstrip_blocks = True
    app.jinja_env.trim_blocks = True
    app.json_encoder = JSONEncoder

    from src import dataspace
    dataspace.init(config_class)
    app.redis = dataspace.rd

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

    migrate.init_app(app, db)
    login_manager.init_app(app)  # TODO: add_context_processor=False
    sio.init_app(app)
    mail.init_app(app)

    if config_class.__name__ != "TestingConfig":
        scheduler.start()

    @app.route("/eegg")
    def hello():
        return "eegg"

    @app.before_request
    def before_request():
        g.request_start_time = time.time()
        g.time_since_request = lambda: "%.5fs" % (time.time() -
                                                  g.request_start_time)

    logger.debug("Adding wiki static folder")
    from src.app.wiki.routing import bp as wiki_bp
    app.register_blueprint(wiki_bp)

    logger.debug("Loading base filters")
    from src.app.views.filters import bp as filters_bp
    app.register_blueprint(filters_bp)

    logger.debug("Loading errors blueprint")
    from src.app.views.errors import bp as errors_bp
    app.register_blueprint(errors_bp)

    logger.debug("Loading api blueprint")
    from src.app.routes import bp as api_bp
    app.register_blueprint(api_bp)

    logger.debug("Loading admin blueprint")
    from src.app.views.admin import bp as admin_bp
    app.register_blueprint(admin_bp)

    logger.debug("Loading auth blueprint")
    from src.app.views.auth import bp as auth_bp
    app.register_blueprint(auth_bp)

    logger.debug("Loading main blueprint")
    from src.app.views.main import bp as main_bp
    app.register_blueprint(main_bp)

    logger.debug("Loading events")
    from src.app import events

    logger.info(f"{app_name} app successfully created")

    return app
