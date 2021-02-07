import json
import logging
import time

from apscheduler.schedulers.background import BackgroundScheduler
import requests

from app import app_name, sio
from app.utils import cache_dir
from config import Config


class Weather:
    def __init__(self, trials: int = 10) -> None:
        self.logger = logging.getLogger(f"{app_name}.services.weather")
        self.trials = trials
        self._file_path = cache_dir/"weather.json"
        self._weather_data = {}
        self.home_city = Config.HOME_CITY
        self.coordinates = Config.HOME_COORDINATES
        self.API_key = Config.DARKSKY_API_KEY
        self.started = False
        self.logger.debug("Weather module has been initialized")

    def update_weather_data(self) -> None:
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
                sio.emit("current_weather", self._weather_data["currently"],
                         namespace="/")
                self.logger.debug("Weather data updated")
                return

    def _start_scheduler(self) -> None:
        self.logger.info("Starting the weather module background scheduler")
        self._scheduler = BackgroundScheduler(daemon=True)
        self._scheduler.add_job(self.update_weather_data,
                                "cron", minute="*/5", misfire_grace_time=5*60,
                                id="weather")
        self._scheduler.start()
        self.logger.debug("The weather module background scheduler has been started")

    def _stop_scheduler(self) -> None:
        self.logger.debug("Stopping the weather module background scheduler")
        self._scheduler.remove_job("weather")
        self._scheduler.shutdown()
        del self._scheduler
        self.logger.debug("The weather module background scheduler has been stopped")

    def _check_recency(self) -> bool:
        if not self._weather_data:
            try:
                with open(self._file_path, "r") as file:
                    self._weather_data = json.load(file)
            except FileNotFoundError:
                return False

        if self._weather_data["currently"]["time"] > time.time() - (15 * 60):
            self.logger.debug(
                "Weather data already up to date")
            return True

        return False

    """API"""
    def start(self) -> None:
        if not self.started:
            if not self._check_recency():
                self.update_weather_data()
            self._start_scheduler()
            self.started = True
        else:
            raise RuntimeError("The weather service is already running")

    def stop(self) -> None:
        if self.started:
            self._stop_scheduler()
            self._weather_data = {}
            self.started = False

    @property
    def data(self) -> dict:
        return self._weather_data

    @property
    def status(self) -> bool:
        return self.started


_weather = Weather()


def start() -> None:
    _weather.start()


def stop() -> None:
    _weather.stop()


def get_data() -> dict:
    return _weather.data


def status() -> bool:
    return _weather.status
