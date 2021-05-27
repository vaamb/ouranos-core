from datetime import date, datetime
import json
import os
import time

import requests

from dataspace import sunTimesData
from utils import base_dir, is_connected, parse_sun_times
from services.template import serviceTemplate
from services.shared_resources import scheduler


class sunTimes(serviceTemplate):
    NAME = "sun_times"
    LEVEL = "base"

    def _init(self):
        self._file_path = None
        self._sun_times_data = sunTimesData
        self.coordinates = self.config.HOME_COORDINATES
        self.started = False

    def update_sun_times_data(self):
        self._logger.debug("Updating sun times")
        if is_connected():
            for i in range(5):
                try:
                    data = requests.get(
                        f"https://api.sunrise-sunset.org/json?lat={self.coordinates[0]}" +
                        f"&lng={self.coordinates[1]}").json()
                    with self.mutex:
                        self._sun_times_data.update(data["results"])
                except ConnectionError:
                    time.sleep(1)
                    continue
                else:
                    with open(self._file_path, "w+") as file:
                        json.dump({**self._sun_times_data}, file)
                    sun_times = {
                        "sunrise": parse_sun_times(
                            self._sun_times_data["sunrise"]),
                        "sunset": parse_sun_times(
                            self._sun_times_data["sunset"]),
                    }
                    try:
                        self.manager.event_dispatcher.put({
                            "event": "sun_times", "data": sun_times
                        })
                    except AttributeError as e:
                        # Discard error when SocketIO has not started yet
                        if "NoneType" not in e.args[0]:
                            raise e
                    self._logger.debug("Sun times data updated")
                    return

        self._logger.error("ConnectionError, cannot update sun times")

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
        self._logger.debug(
            "Sun times data already up to date")
        return True

    def _start(self):
        cache_dir = base_dir / "cache"
        if not cache_dir.exists():
            os.mkdir(cache_dir)
        self._file_path = cache_dir / "sun_times.json"
        if not self._check_recency():
            self.update_sun_times_data()
        scheduler.add_job(self.update_sun_times_data, "cron", hour="1",
                          misfire_grace_time=15 * 60, id="suntimes")

    def _stop(self):
        scheduler.remove_job("suntimes")
        self._sun_times_data.clear()

    """Functions to pass data to higher modules"""
    def get_data(self):
        return self._sun_times_data
