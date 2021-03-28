import json
import os
import time

import requests

from app import sio, scheduler
from config import Config, base_dir
from app.services.template import serviceTemplate


class Weather(serviceTemplate):
    NAME = "weather"
    LEVEL = "app"

    def _init(self) -> None:
        self._file_path = None
        self._weather_data = {}
        self._coordinates = Config.HOME_COORDINATES
        self._API_key = Config.DARKSKY_API_KEY
        self._started = False

    def update_weather_data(self) -> None:
        self._logger.debug("Updating weather data")
        for i in range(5):
            try:
                parameters = {"exclude": ["minutely", "alerts", "flags"],
                              "units": "ca"}  # ca units = SI units with speed in km/h rather than m/s
                data = requests.get(
                    f"https://api.darksky.net/forecast/{self._API_key}/" +
                    f"{self._coordinates[0]},{self._coordinates[1]}",
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
                try:
                    sio.emit("current_weather",
                             self._weather_data["currently"],
                             namespace="/")
                except AttributeError as e:
                    # Discard error when SocketIO has not started yet
                    if "NoneType" not in e.args[0]:
                        raise e
                self._logger.debug("Weather data updated")
                return

    def _check_recency(self) -> bool:
        if not self._weather_data:
            try:
                with open(self._file_path, "r") as file:
                    self._weather_data = json.load(file)
            except FileNotFoundError:
                return False

        if self._weather_data["currently"]["time"] > \
                time.time() - (Config.WEATHER_UPDATE_PERIOD * 60):
            self._logger.debug("Weather data already up to date")
            return True

        return False

    def _start(self) -> None:
        cache_dir = base_dir / "cache"
        if not cache_dir.exists():
            os.mkdir(cache_dir)
        self._file_path = cache_dir/"weather.json"
        if not self._check_recency():
            self.update_weather_data()
        scheduler.add_job(self.update_weather_data, "cron",
                          minute=f"*/{Config.WEATHER_UPDATE_PERIOD}",
                          misfire_grace_time=5 * 60, id="weather")

    def _stop(self) -> None:
        scheduler.remove_job("weather")
        self._weather_data = {}

    """API"""
    def get_data(self) -> dict:
        return self._weather_data
