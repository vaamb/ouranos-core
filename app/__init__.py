import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from flask import json, Flask
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_moment import Moment
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO

from config import Config


START_TIME = datetime.now(timezone.utc)

app_name = Config.APP_NAME
root_path = Path(__file__).absolute().parents[0]

logger = logging.getLogger(app_name)

scheduler = BackgroundScheduler()
login_manager = LoginManager()
db = SQLAlchemy()
migrate = Migrate()
sio = SocketIO(json=json)
moment = Moment()


def create_app(config_class=Config):
    logger.info(f"Starting {app_name} ...")
    app = Flask(app_name, root_path=root_path)

    app.config.from_object(config_class)
    app.jinja_env.lstrip_blocks = True
    app.jinja_env.trim_blocks = True

    if not os.path.exists('logs'):
        os.mkdir('logs')

    # Init db
    db.init_app(app)
    from app.models import Role, comChannel
    with app.app_context():
        try:
            db.create_all()
            Role.insert_roles()
            comChannel.insert_channels()
        except Exception as e:
            print(e)

    migrate.init_app(app, db)
    login_manager.init_app(app)
    sio.init_app(app)
    moment.init_app(app)
    scheduler.start()

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

    from app import database
    from app import socketio_events

    logger.info(f"{app_name} successfully started")

    return app
