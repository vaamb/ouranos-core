import logging
from datetime import datetime, timezone
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from flask import json, Flask
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO
from flask_mail import Mail

from config import Config, DevelopmentConfig

START_TIME = datetime.now(timezone.utc)

app_name = Config.APP_NAME
root_path = Path(__file__).absolute().parents[0]

logger = logging.getLogger(app_name)

scheduler = BackgroundScheduler()
login_manager = LoginManager()
db = SQLAlchemy()
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
    app = Flask(app_name, root_path=root_path)

    app.config.from_object(config_class)
    app.jinja_env.lstrip_blocks = True
    app.jinja_env.trim_blocks = True



    # Init db
    db.init_app(app)
    from app.models import Role, comChannel
    with app.app_context():
        try:
            db.create_all()
            Role.insert_roles()
            comChannel.insert_channels()
        except Exception as e:
            logger.error(e)

    migrate.init_app(app, db)
    login_manager.init_app(app)
    # TODO: catch if use REDIS and add "message_queue=$redis_url"
    sio.init_app(app)
    mail.init_app(app)
    scheduler.start()

    import dataspace
    dataspace.init(config_class)
    app.redis = dataspace.rd

    @app.route("/eegg")
    def hello():
        return "eegg"

    from app.views.errors import bp as errors_bp
    app.register_blueprint(errors_bp)

    from app.views.auth import bp as auth_bp
    app.register_blueprint(auth_bp)

    from app.views.main import bp as main_bp
    app.register_blueprint(main_bp)

    from app.views.admin import bp as admin_bp
    app.register_blueprint(admin_bp)

    from app.views.api import bp as api_bp
    app.register_blueprint(api_bp)

#    from app import database
    from app import socketio_events

    logger.info(f"{app_name} app successfully created")

    return app
