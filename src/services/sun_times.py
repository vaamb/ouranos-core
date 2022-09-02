from datetime import date, datetime
import json
import os

import requests

from src.core.g import base_dir
from src.services.template import ServiceTemplate
from src.services.shared_resources import scheduler
from src.utils import is_connected, parse_sun_times


class SunTimes(ServiceTemplate):
    LEVEL = "app"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._file_path = None
        self.coordinates = self.config.HOME_COORDINATES

    def update_sun_times_data(self):
        self.logger.debug("Updating sun times")
        if is_connected():
            try:
                latitude = self.coordinates[0]
                longitude = self.coordinates[1]
                data = requests.get(
                    f"https://api.sunrise-sunset.org/json",
                    params={"lat": latitude, "lng": longitude},
                    timeout=1.0,
                    verify=False,
                ).json()
                with self.mutex:
                    core.api.weather.update_sun_times(data["results"])
            except requests.exceptions.ConnectionError:
                with self.mutex:
                    core.api.weather.clear_sun_times()
                    self.logger.error(
                        "ConnectionError, cannot update sun times")
            else:
                with open(self._file_path, "w+") as file:
                    json.dump(data["results"], file)
                sun_times = {
                    "sunrise": parse_sun_times(
                        data["results"]["sunrise"]),
                    "sunset": parse_sun_times(
                        data["results"]["sunset"]),
                }
                try:
                    self.manager.dispatcher.emit(
                        "application", "sun_times", data=sun_times
                    )
                except AttributeError as e:
                    # Discard error when SocketIO has not started yet
                    if "NoneType" not in e.args[0]:
                        raise e
                self.logger.debug("Sun times data updated")
        else:
            with self.mutex:
                core.api.weather.clear_sun_times()
                self.logger.error("ConnectionError, cannot update sun times")

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
            core.api.weather.update_sun_times(data)
        self.logger.debug(
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
        core.api.weather.clear_sun_times()


info = {
    "time": "timestamp",
    "description": "description",
    "icon": "icon",
    "weather": {
        "temperature": 1,
        "temperature_max": 1,
        "temperature_min": 1,
        "humidity": 1,
        "humidity_max": 1,
        "humidity_min": 1,
        "dew_point": 1,
        "wind_speed": 1,
        "precip_probability": 1,
        "precip_intensity": 1,
        "cloud_cover": 1,
    },
}

current_and_daily = dict(info).update({
    "sky_events": {
        "sunrise": 1,
        "sunset": 1,
        "moonrise": 1,
        "moonset": 1,
    }
})
