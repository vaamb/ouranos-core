from datetime import datetime
import logging
import logging.config
from logging.handlers import SMTPHandler, RotatingFileHandler
import os

from flask import Flask
from flask_socketio import SocketIO
#from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager

from config import Config
from app.gaiaDatabase import gaiaDatabase
from app.database import db_session, init_db
from gaiaConfig import LOGGING_CONFIG

socketio = SocketIO()

db2 = gaiaDatabase()

#db = SQLAlchemy()

migrate = Migrate()
login_manager = LoginManager()
login_manager.login_view = 'auth.login'

#Load after as it requires login_manager and need to use insert_roles()
from app.models import Role, Measure

def create_app(test_config = None, debug = False):
    app = Flask(__name__, instance_relative_config = True)
    app.config.from_object(Config)
    app.START_TIME = datetime.now()

    if not os.path.exists('logs'):
        os.mkdir('logs')
    logging.config.dictConfig(LOGGING_CONFIG)
    app.logger = logging.getLogger("gaia")
    app.logger.info('gaiaWeb startup')



    
    app.logger.info("Initialising SQLAlchemy")
    init_db()
    Role.insert_roles() #Create or update users roles
    Measure.insert_measures()
    app.logger.info("SQLAlchemy initialised")

#    logger.info("Initialising Alambic")
#    migrate.init_app(app, db)
#    logger.info("Alembic initialised")

    login_manager.init_app(app)

    app.logger.info("Initializing soketIO")
    socketio.init_app(app)

    app.debug = debug
    if not app.debug:
        if app.config['MAIL_SERVER']:
            auth = None
            if app.config['MAIL_USERNAME'] or app.config['MAIL_PASSWORD']:
                auth = (app.config['MAIL_USERNAME'], app.config['MAIL_PASSWORD'])
            secure = None
            if app.config['MAIL_USE_TLS']:
                secure = ()
                mail_handler = SMTPHandler(
                mailhost = (app.config['MAIL_SERVER'], app.config['MAIL_PORT']),
                fromaddr = 'no-reply@' + app.config['MAIL_SERVER'],
                toaddrs = app.config['ADMINS'], subject = 'GaiaWeb Failure',
                credentials=auth, secure=secure)
            mail_handler.setLevel(logging.ERROR)
            app.logger.addHandler(mail_handler)


        

    @app.route("/eegg")
    def hello():
        return (app.start)

    from .auth import bp as auth_bp
    app.register_blueprint(auth_bp)

    from app.main import bp as main_bp
    app.register_blueprint(main_bp)
    
    from app.errors import bp as errors_bp
    app.register_blueprint(errors_bp)

    from app.admin import bp as admin_bp
    app.register_blueprint(admin_bp)

    END_LOADING = datetime.now()
    load_time = END_LOADING - app.START_TIME
    app.logger.info('gaiaWeb loaded in {},{:02d} seconds'
                    .format(str(load_time.seconds),
                            int(round(load_time.microseconds/10**4))
                            ))
    
    return app