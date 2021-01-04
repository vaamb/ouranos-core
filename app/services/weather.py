import json
import logging
import os
from pathlib import Path
import socket
import time

from apscheduler.schedulers.background import BackgroundScheduler
import requests

from app import app_name
from config import Config


cache_dir = Path(__file__).absolute().parents[2]/"cache"
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


class Weather:
    def __init__(self, trials=10):
        self.logger = logging.getLogger(f"{app_name}.services.weather")
        self.trials = trials
        self._file_path = cache_dir/"weather.json"
        self._weather_data = {}
        self.home_city = Config.HOME_CITY
        self.coordinates = Config.HOME_COORDINATES
        self.API_key = Config.DARKSKY_API_KEY
        self.started = False
        self.logger.debug("Weather module has been initialized")

    def update_weather_data(self):
        self.logger.debug("Updating weather data")
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
                with open(self._file_path, "w+") as file:
                    json.dump(self._weather_data, file)
                self.logger.debug("Weather data updated")
                return

    def _start_scheduler(self):
        self.logger.info("Starting the weather module background scheduler")
        self._scheduler = BackgroundScheduler(daemon=True)
        self._scheduler.add_job(self.update_weather_data,
                                "cron", minute="*/15", misfire_grace_time=5*60,
                                id="weather")
        self._scheduler.start()
        self.logger.debug("The weather module background scheduler has been started")

    def _stop_scheduler(self):
        self.logger.debug("Stopping the weather module background scheduler")
        self._scheduler.remove_job("weather")
        self._scheduler.shutdown()
        del self._scheduler
        self.logger.debug("The weather module background scheduler has been stopped")

    def _check_recency(self):
        if not self._weather_data:
            try:
                file = open(self._file_path, "r")
            except FileNotFoundError:
                return False
            data = json.load(file)
            file.close()
            if data["currently"]["time"] > time.time() - (15 * 60):
                self._weather_data = data
                return True
            return False
        return True

    """API"""
    def start(self):
        if not self.started:
            if not self._check_recency():
                self.update_weather_data()
            self._start_scheduler()
            self.started = True
            return
        else:
            raise RuntimeError("The weather service is already running")


    def stop(self):
        if self.started:
            self._stop_scheduler()
            self._weather_data = {}
            self.started = False

    @property
    def data(self):
        return self._weather_data

    @property
    def status(self):
        return self.started


_weather = Weather()


def start():
    _weather.start()


def stop():
    _weather.stop()


def get_data():
    return _weather.data


def status():
    return _weather.status
