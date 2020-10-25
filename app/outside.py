# -*- coding: utf-8 -*-
import os
import time
from pathlib import Path
import socket
import logging
import json

import requests
from apscheduler.schedulers.background import BackgroundScheduler

from config import Config


cache_dir = Path(__file__).absolute().parents[1]/"cache"
if not cache_dir:
    os.mkdir(cache_dir)


def is_connected():
    try:
        host = socket.gethostbyname(Config.TEST_CONNECTION_IP)
        s = socket.create_connection((host, 80), 2)
        s.close()
        return True
    except Exception as ex:
        print(ex)
    return False


class Outside:
    def __init__(self, trials=10):
        self.logger = logging.getLogger("gaia.weather")
        self.logger.info("Initializing weather module")
        self.trials = trials
        self._file_path = cache_dir/"weather.json"
        self._weather_data = {}
        self._moments_data = {}
        self.home_city = Config.HOME_CITY
        self.coordinates = Config.HOME_COORDINATES
        self.API_key = Config.DARKSKY_API_KEY
        self.logger.info("Weather module has been initialized")

    def update_weather_data(self):
        if is_connected():
            for i in range(self.trials):
                try:
                    parameters = {"exclude": ["minutely", "alerts", "flags"],
                                  "units": "ca"}  # ca units = SI units with speed in km/h rather than m/s
                    data = requests.get(
                        f"https://api.darksky.net/forecast/{self.API_key}/" +
                        f"{self.coordinates[0]},{self.coordinates[1]}",
                        params=parameters).json()
                    self._weather_data = {"currently": data["currently"],
                                          "hourly": data["hourly"]["data"],
                                          "daily": data["daily"]["data"]}
                except ConnectionError:
                    time.sleep(1)
                    continue
                else:
                    with open(self._file_path, "w") as file:
                        json.dump(self._weather_data, file)
                    return
        self.logger.error("ConnectionError, cannot update weather data")

    def update_moments_data(self):
        if is_connected():
            for i in range(self.trials):
                try:
                    data = requests.get(
                        f"https://api.sunrise-sunset.org/json?lat={self.coordinates[0]}" +
                        f"&lng={self.coordinates[1]}").json()
                    self._moments_data = data["results"]
                    return
                except ConnectionError:
                    time.sleep(1)
                    continue
        self.logger.error("ConnectionError, cannot update moments of the day")

    def _start_scheduler(self):
        self.logger.debug("Starting the weather module background scheduler")
        self._scheduler = BackgroundScheduler(daemon=True)
        self._scheduler.add_job(self.update_weather_data,
                                "cron", minute="*/15", misfire_grace_time=5*60,
                                id="weather")
        self._scheduler.add_job(self.update_moments_data,
                                "cron", hour="1", misfire_grace_time=15*60,
                                id="moments")
        self._scheduler.start()
        self.logger.debug("The weather module background scheduler has been started")

    def _stop_scheduler(self):
        self.logger.debug("Stopping the weather module background scheduler")
        self._scheduler.remove_job("weather")
        self._scheduler.remove_job("moments")
        self._scheduler.shutdown()
        del self._scheduler
        self.logger.debug("The weather module background scheduler has been stopped")

    def _check_recency(self):
        if not self._weather_data:
            file = open(self._file_path, "r")
            data = json.load(file)
            file.close()
            if data["currently"]["time"] > time.time() - (15 * 60):
                self._weather_data = data
                return True
        return False

    def start(self):
        if not self._check_recency():
            self.update_weather_data()
        self.update_moments_data()
        self._start_scheduler()

    def stop(self):
        self._stop_scheduler()

    """Functions to pass data to higher modules"""
    @property
    def weather_data(self):
        return self._weather_data

    @property
    def moments_data(self):
        return self._moments_data
