import os
from pathlib import Path

app_dir = Path.cwd().resolve()

class Config(object):
    #Flask config 
    SECRET_KEY = os.environ.get("SECRET_KEY") or "BXhNmCEmNdoBNngyGXj6jJtooYAcKpt6"

    #SQLAlchemy config
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
    'sqlite:///' + os.path.join(app_dir, 'app.db')
#    SQLALCHEMY_DATABASE_URI = 'mysql://Sensors:Adansonia7!@localhost/Gaia'    
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    #Mail config
    MAIL_SERVER = os.environ.get('MAIL_SERVER')
    MAIL_PORT = int(os.environ.get('MAIL_PORT') or 25)
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS') is not None
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')

    #GAIA config
    GAIA_ADMIN = ['valentin.ambroise@outlook.com']
    REMOTE_SERVER = "one.one.one.one"

    #Data logging
    RESOURCES_FREQUENCY = 5
    ENVIRONMENT_FREQUENCY = 10
    PLANT_FREQUENCY = 15