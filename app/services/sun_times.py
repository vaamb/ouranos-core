from datetime import date, datetime
import json
import logging
import os
import time

from apscheduler.schedulers.background import BackgroundScheduler
import requests

from app import app_name
from app.utils import is_connected
from config import Config, base_dir


class sunTimes:
    def __init__(self, trials=10):
        self.logger = logging.getLogger(f"{app_name}.services.suntimes")
        self.logger.info("Initializing sun_times module")
        self.trials = trials
        self._file_path = None
        self._sun_times_data = {}
        self.coordinates = Config.HOME_COORDINATES
        self.started = False
        self.logger.debug("suntimes module has been initialized")

    def update_sun_times_data(self):
        self.logger.debug("Updating sun times")
        if is_connected():
            for i in range(self.trials):
                try:
                    data = requests.get(
                        f"https://api.sunrise-sunset.org/json?lat={self.coordinates[0]}" +
                        f"&lng={self.coordinates[1]}").json()
                    self._sun_times_data = data["results"]
                    self.logger.debug("Sun times data updated")
                except ConnectionError:
                    time.sleep(1)
                    continue
                else:
                    with open(self._file_path, "w+") as file:
                        json.dump(self._sun_times_data, file)
                    self.logger.debug("Sun times data updated")
                    return

        self.logger.error("ConnectionError, cannot update sun times")

    def _start_scheduler(self):
        self.logger.info("Starting the suntimes service background scheduler")
        self._scheduler = BackgroundScheduler(daemon=True)
        self._scheduler.add_job(self.update_sun_times_data,
                                "cron", hour="1", misfire_grace_time=15*60,
                                id="suntimes")
        self._scheduler.start()
        self.logger.debug("The suntimes service background scheduler has been started")

    def _stop_scheduler(self):
        self.logger.debug("Stopping the suntimes service background scheduler")
        self._scheduler.remove_job("suntimes")
        self._scheduler.shutdown()
        del self._scheduler
        self.logger.debug("The suntimes service background scheduler has been stopped")

    def _check_recency(self) -> bool:
        try:
            update_epoch = self._file_path.stat().st_ctime
            update_dt = datetime.fromtimestamp(update_epoch)
        except FileNotFoundError:
            return False

        if update_dt.date() < date.today():
            return False

        with open(self._file_path, "r") as file:
            data = json.load(file)
        self._sun_times_data = data
        self.logger.debug(
            "Sun times data already up to date")
        return True

    def start(self):
        if not self.started:
            cache_dir = base_dir / "cache"
            if not cache_dir.exists():
                os.mkdir(cache_dir)
            self._file_path = cache_dir / "sun_times.json"
            if not self._check_recency():
                self.update_sun_times_data()
            self._start_scheduler()
            self.started = True
        else:
            raise RuntimeError("The suntimes service is already running")

    def stop(self):
        if self.started:
            self._stop_scheduler()
            self._sun_times_data = {}
            self.started = False

    """Functions to pass data to higher modules"""
    @property
    def data(self):
        return self._sun_times_data

    @property
    def status(self):
        return self.started


_sun_times = sunTimes()


def start():
    _sun_times.start()


def stop():
    _sun_times.stop()


def get_data():
    return _sun_times.data


def status():
    return _sun_times.status
