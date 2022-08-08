from datetime import datetime
import json
import os
import threading
import time

import requests

from src.cache import weatherData
from src.consts import WEATHER_MEASURES
from src.services.template import ServiceTemplate
from src.services.shared_resources import scheduler
from src.utils import base_dir, is_connected


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


class Weather(ServiceTemplate):
    LEVEL = "app"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._file_path = None
        self._data = weatherData
        # TODO: use coordinates from geolocalisation
        #  Shutdown if no HOME_COORDINATES
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
            "application", "weather_current",
            data={"currently": self._data["currently"]},
        )
        if now.minute % 15 == 0:
            self.manager.dispatcher.emit(
                "application", "weather_hourly",
                data={"hourly": self._data["hourly"]},
            )
        if now.hour % 3 == 0 and now.minute == 0:
            self.manager.dispatcher.emit(
                "application", "weather_daily",
                data={"daily": self._data["daily"]},
            )

    def update_weather_data(self) -> None:
        if is_connected():
            self.logger.debug("Trying to update weather data")
            try:
                parameters = {
                    "exclude": ["minutely", "alerts", "flags"],
                    "units": "ca",  # ca units = SI units with speed in km/h rather than m/s
                }
                data = requests.get(
                    f"https://api.darksky.net/forecast/{self._API_key}/" +
                    f"{self._coordinates[0]},{self._coordinates[1]}",
                    params=parameters, timeout=3.0
                ).json()
            except requests.exceptions.ConnectionError:
                self.logger.error("ConnectionError: cannot update weather data")
                with self.mutex:
                    self._data.clear()
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
                self.logger.debug("Weather data updated")
        else:
            self.logger.error("ConnectionError: could not update weather data")
            with self.mutex:
                self._data.clear()

    def _check_recency(self) -> bool:
        if not self._data:
            try:
                with open(self._file_path, "r") as file:
                    self._load_data(json.load(file))
            except (FileNotFoundError, json.decoder.JSONDecodeError):
                # No file or empty file
                return False

        if self._data["currently"]["time"] > \
                time.time() - (self.config.OURANOS_WEATHER_UPDATE_PERIOD * 60):
            self.logger.debug("Weather data already up to date")
            return True

        return False

    def _start(self) -> None:
        cache_dir = base_dir / "cache"
        if not cache_dir.exists():
            os.mkdir(cache_dir)
        self._file_path = cache_dir / "weather.json"
        if not self._check_recency():
            # TODO: use threadpool, attach it to the manager class?
            thread = threading.Thread(target=self.update_weather_data)
            thread.start()
            #thread.join()
        scheduler.add_job(self.update_weather_data, "cron",
                          minute=f"*/{self.config.OURANOS_WEATHER_UPDATE_PERIOD}",
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
