from apscheduler.schedulers.background import BackgroundScheduler
from database import Base, SQLAlchemyWrapper


scheduler = BackgroundScheduler()
db = SQLAlchemyWrapper(model=Base)


class registerEventMixin:
    def _register_dispatcher_events(self, dispatcher):
        for key in dir(self):
            if key.startswith("dispatch_"):
                event = key.replace("dispatch_", "")
                callback = getattr(self, key)
                dispatcher.on(event, callback)
