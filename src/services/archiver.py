from datetime import datetime, timedelta, timezone
from multiprocessing import Process, Queue

from dispatcher import STOP_SIGNAL
from flask_sqlalchemy import Model
from sqlalchemy import inspect

from src.core.database.models import gaia, archives
from src.services.shared_resources import db, scheduler
from src.services.template import ServiceTemplate


number_of_processes = 1


class Archiver(ServiceTemplate):
    LEVEL = "base"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._mapping = {}
        self.archive_limit = {
            "sensor": 180,
            "health": 360,
            "system": 90
        }
        self.map_archives()
        self._task_list = Queue()
        self._task_done = Queue()
        self._processes = []
        for process in range(number_of_processes):
            p = Process(target=self.mp_loop)
            # TODO: use celery
            # p.start()
            self._processes.append(p)
    
    def _start(self):
        scheduler.add_job(self.archive_loop, "cron", hour="1", day_of_week="0",
                          misfire_grace_time=60 * 60, id="archiver")
    
    def _stop(self):
        self._task_list.put(STOP_SIGNAL)
        for p in self._processes:
            p.join()
        scheduler.remove_job("archiver")

    def map_archives(self):
        models_ = [
            cls for name, cls in [
                *archives.__dict__.items(),
                *gaia.__dict__.items(),
            ]
            if isinstance(cls, type) and issubclass(cls, Model)
        ]
        for model in models_:
            link = getattr(model, '__archive_link__', None)
            if link:
                try:
                    self._mapping[link.name].update({link.status: model})
                except KeyError:
                    self._mapping[link.name] = {link.status: model}

    def archive_loop(self):
        self.map_archives()
        for data in self._mapping:
            if all(k in self._mapping[data] for k in ("recent", "archive")):
                recent = self._mapping[data]["recent"]
                archive = self._mapping[data]["archive"]
                self.archive(data, recent, archive)
                # TODO: use celery
                # task = (data, recent, archived)
                # self._task_list.put(task)
            else:
                if "archive" not in self._mapping[data]:
                    self.logger.warning(f"Data '{data}' only has recent table "
                                         f"and cannot be archived")
                else:
                    self.logger.warning(f"Data '{data}' does not have any "
                                         f"recent table, no archiving possible")

    def archive(self, data_name, recent_model, archive_model):
        days_limit = self.archive_limit.get(data_name, 180)
        now_utc = datetime.now(timezone.utc)
        time_limit = now_utc - timedelta(days=days_limit)
        columns = inspect(recent_model).columns.keys()
        get_columns = lambda data: {column: getattr(data, column)
                                    for column in columns}
        with db.scoped_session() as session:
            old_data = (session.query(recent_model)
                        .filter(recent_model.datetime < time_limit))
            session.bulk_insert_mappings(
                archive_model, (get_columns(data) for data in old_data)
            )
            old_data.delete()
            session.commit()

    # TODO: finish to use multiprocessor
    def mp_loop(self):
        while True:
            task = self._task_list.get()
            if task == STOP_SIGNAL:
                self._task_list.put(STOP_SIGNAL)
                break
            self.archive(task[0], task[1], task[2])
