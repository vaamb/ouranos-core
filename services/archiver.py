from datetime import datetime, timedelta, timezone
from multiprocessing import Process, Queue

from flask_sqlalchemy import Model
from sqlalchemy import inspect

from app import models
from dataspace import STOP_SIGNAL
from services.shared_resources import db, scheduler
from services.template import serviceTemplate


number_of_processes = 1

archive_limit = {
    "sensor": 180,
    "health": 360,
    "system": 90
}


class Archiver(serviceTemplate):
    NAME = "archiver"
    LEVEL = "base"

    def _init(self):
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
        result = {}
        models_ = [cls for name, cls in models.__dict__.items()
                   if isinstance(cls, type) and issubclass(cls, Model)]
        for model in models_:
            link = getattr(model, '__archive_link__', None)
            if link:
                try:
                    result[link.name].update({link.status: model})
                except KeyError:
                    result[link.name] = {link.status: model}
        return result

    def archive_loop(self):
        mapping = self.map_archives()
        for data in mapping:
            if all(k in mapping[data] for k in ("recent", "archive")):
                recent = mapping[data]["recent"]
                archive = mapping[data]["archive"]
                self.archive(data, recent, archive)
                # TODO: use celery
                # task = (data, recent, archived)
                # self._task_list.put(task)
            else:
                if "archive" not in mapping[data]:
                    self._logger.warning(f"Data '{data}' only has recent table "
                                         f"and cannot be archived")
                else:
                    self._logger.warning(f"Data '{data}' does not have any "
                                         f"recent table, no archiving possible")

    def archive(self, data_name, recent_model, archive_model):
        days_limit = archive_limit.get(data_name, 180)
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

    def mp_loop(self):
        while True:
            task = self._task_list.get()
            if task == STOP_SIGNAL:
                self._task_list.put(STOP_SIGNAL)
                break
            self.archive(task[0], task[1], task[2])
