from apscheduler.schedulers.background import BackgroundScheduler

from src.database import SQLAlchemyWrapper


scheduler = BackgroundScheduler()
db = SQLAlchemyWrapper()
