from apscheduler.schedulers.background import BackgroundScheduler
from database import Base, SQLAlchemyWrapper

scheduler = BackgroundScheduler()
db = SQLAlchemyWrapper(model=Base)
