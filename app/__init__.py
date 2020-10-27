import logging
import os

from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_moment import Moment
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO

from config import Config

# TODO: move app_name in config
app_name = "gaiaWeb"

logger = logging.getLogger(app_name)

scheduler = BackgroundScheduler()
login_manager = LoginManager()
db = SQLAlchemy()
migrate = Migrate()
sio = SocketIO()
moment = Moment()


def create_app(config_class=Config):
    logger.info(f"Initializing Flask app...")
    app = Flask(app_name)

    app.config.from_object(config_class)
    app.jinja_env.lstrip_blocks = True
    app.jinja_env.trim_blocks = True

    if not os.path.exists('logs'):
        os.mkdir('logs')

    db.init_app(app)

    from app.models import Role
    with app.app_context():
        # db.create_all()
        Role.insert_roles()

    migrate.init_app(app, db)
    login_manager.init_app(app)
    sio.init_app(app)
    moment.init_app(app)
    scheduler.start()

    @app.route("/eegg")
    def hello():
        return "eegg"

    from app.errors import bp as errors_bp
    app.register_blueprint(errors_bp)

    from .auth import bp as auth_bp
    app.register_blueprint(auth_bp)

    from app.main import bp as main_bp
    app.register_blueprint(main_bp)

    from app.admin import bp as admin_bp
    app.register_blueprint(admin_bp)

#    from app.api import bp as api_bp
#    app.register_blueprint(api_bp)

    from app import models
    from app import database
    from app import socketio_events

    logger.info(f"Flask app successfully initialized")

    return app
