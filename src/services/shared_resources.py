from apscheduler.schedulers.background import BackgroundScheduler
from src.database import Base, SQLAlchemyWrapper


scheduler = BackgroundScheduler()
db = SQLAlchemyWrapper(model=Base)
