from apscheduler.schedulers.background import BackgroundScheduler

from ouranos.core import SQLAlchemyWrapper


scheduler = BackgroundScheduler()
db = SQLAlchemyWrapper()
