from apscheduler.schedulers.background import BackgroundScheduler

from src.core.database import SQLAlchemyWrapper


scheduler = BackgroundScheduler()
db = SQLAlchemyWrapper()
