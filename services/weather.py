from datetime import datetime
import json
import os
import time

import requests

from dataspace import WEATHER_MEASURES, weatherData
from services.template import serviceTemplate
from services.shared_resources import scheduler
from utils import base_dir


def _simplify_weather_data(weather_data) -> dict:
    return {
        measure: weather_data[measure]
        for measure in WEATHER_MEASURES["mean"] +
                       WEATHER_MEASURES["mode"] +
                       WEATHER_MEASURES["other"]
        if measure in weather_data
    }


def _format_forecast(forecast, time_window):
    if time_window > len(forecast):
        time_window = len(forecast) - 1

    return {
        "time_window": {
            "start": forecast[0]["time"],
            "end": forecast[time_window - 1]["time"]
        },
        "forecast": [_simplify_weather_data(forecast[_])
                     for _ in range(time_window)],
    }


class Weather(serviceTemplate):
    NAME = "weather"
    LEVEL = "app"

    def _init(self) -> None:
        self._file_path = None
        self._data = weatherData
        self._coordinates = self.config.HOME_COORDINATES
        self._API_key = self.config.DARKSKY_API_KEY
        self._started = False

    def _load_data(self, raw_data):
        with self.mutex:
            self._data.update({
                "currently": _simplify_weather_data(raw_data["currently"]),
                "hourly": _format_forecast(raw_data["hourly"],
                                           time_window=48),
                "daily": _format_forecast(raw_data["daily"],
                                          time_window=14),
            })

    def _send_events(self):
        now = datetime.now()
        self.manager.dispatcher.emit(
            "Socket.IO", "current_weather", data=self._data["currently"]
        )
        if now.minute % 15 == 0:
            self.manager.dispatcher.emit(
                "Socket.IO", "hourly_weather", data=self._data["hourly"]
            )
        if now.hour % 3 == 0 and now.minute == 0:
            self.manager.dispatcher.emit(
                "Socket.IO", "daily_weather", data=self._data["daily"]
            )

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
            except ConnectionError:
                time.sleep(1)
                continue
            else:
                raw_data = {
                    "currently": data["currently"],
                    "hourly": data["hourly"]["data"],
                    "daily": data["daily"]["data"]
                }
                self._load_data(raw_data)
                with open(self._file_path, "w+") as file:
                    json.dump(raw_data, file)
                self._send_events()
                self._logger.debug("Weather data updated")
                return

    def _check_recency(self) -> bool:
        if not self._data:
            try:
                with open(self._file_path, "r") as file:
                    self._load_data(json.load(file))
            except (FileNotFoundError, json.decoder.JSONDecodeError):
                # No file or empty file
                return False

        if self._data["currently"]["time"] > \
                time.time() - (self.config.WEATHER_UPDATE_PERIOD * 60):
            self._logger.debug("Weather data already up to date")
            return True

        return False

    def _start(self) -> None:
        cache_dir = base_dir / "cache"
        if not cache_dir.exists():
            os.mkdir(cache_dir)
        self._file_path = cache_dir / "weather.json"
        if not self._check_recency():
            self.update_weather_data()
        scheduler.add_job(self.update_weather_data, "cron",
                          minute=f"*/{self.config.WEATHER_UPDATE_PERIOD}",
                          misfire_grace_time=5 * 60, id="weather")

    def _stop(self) -> None:
        scheduler.remove_job("weather")
        self._data.clear()

    """API"""

    @property
    def data(self):
        return self._data

    @property
    def current_data(self) -> dict:
        return self._data["currently"]

    @property
    def hourly_data(self) -> dict:
        return self._data["hourly"]

    @property
    def daily_data(self) -> dict:
        return self._data["daily"]
