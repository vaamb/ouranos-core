from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone
from logging import getLogger, Logger
import os
import time

import aiofiles
from aiohttp import ClientError, ClientSession

from ouranos import current_app, scheduler
from ouranos.core.config.consts import WEATHER_MEASURES
from ouranos.core.utils import DispatcherFactory, stripped_warning
from ouranos.sdk import api, json


_weather_recency_limit = 6
_weather_file = "weather.json"
_sun_times_file = "sun_times.json"


async def is_connected(ip_to_connect: str = "1.1.1.1", port: int = 80) -> bool:
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(ip_to_connect, port), 2
        )
        writer.close()
        return True
    except Exception as ex:
        stripped_warning(ex)
    return False


def _filter_weather_data(weather_data: dict) -> dict:
    """Filter weather_data to only keep a subset of it
    :param weather_data: the data from
    :return: the filtered data
    """
    return {
        measure: weather_data[measure]
        for measure in WEATHER_MEASURES["mean"] +
                       WEATHER_MEASURES["mode"] +
                       WEATHER_MEASURES["other"]
        if measure in weather_data
    }


def _format_forecast(forecast: list, time_window: int) -> dict:
    if time_window >= len(forecast):
        time_window = len(forecast) - 1

    return {
        "time_window": {
            "start": forecast[0]["time"],
            "end": forecast[time_window]["time"]
        },
        "forecast": [
            _filter_weather_data(forecast[i]) for i in range(time_window)
        ],
    }


def format_weather_data(raw_data: dict) -> dict:
    return {
        "currently": _filter_weather_data(raw_data["currently"]),
        "hourly": _format_forecast(raw_data["hourly"], time_window=48),
        "daily": _format_forecast(raw_data["daily"], time_window=14),
    }


def _parse_sun_times(moment: str | datetime) -> datetime:
    if isinstance(moment, datetime):
        return moment
    _time = datetime.strptime(moment, "%I:%M:%S %p").time()
    return datetime.combine(date.today(), _time, tzinfo=timezone.utc)


def format_sun_times_data(data: dict[str, str]) -> dict[str, datetime | str]:
    return {
        event: _parse_sun_times(timestamp) for event, timestamp in data.items()
        if event != "day_length"
    }


class SkyWatcher:
    def __init__(self, ):
        self.logger: Logger = getLogger("ouranos.aggregator")
        self.dispatcher = DispatcherFactory.get("aggregator")
        self._mutex = asyncio.Lock()
        # TODO: use coordinates from geolocalisation
        #  Shutdown if no HOME_COORDINATES
        self._coordinates = current_app.config.get("HOME_COORDINATES")
        self._API_key = current_app.config.get("DARKSKY_API_KEY")

    """Weather"""
    async def _check_weather_recency(self) -> bool:
        """Return True is weather data is recent (less than 5 min)"""
        if api.weather.get("currently") is None:
            try:
                path = current_app.cache_dir/_weather_file
                async with aiofiles.open(path, "r") as file:
                    data_raw = await file.read()
                data = json.loads(data_raw)
            except (FileNotFoundError, ValueError):
                # No file or empty file
                return False
            else:
                api.weather.update(data)
        time_ = api.weather.get("currently", {}).get("time")
        if time_ is None:
            return False
        update_period: int = current_app.config.get("WEATHER_UPDATE_PERIOD")
        if time_ > time.time() - (update_period * 60):
            self.logger.debug("Weather data already up to date")
            return True
        return False

    async def clear_old_weather_data(self):
        path = current_app.cache_dir/_weather_file
        time_ = api.weather.get("currently", {}).get("time")
        # If weather "current" time older than _weather_recency_limit hours: clear
        if time_ < time.time() - _weather_recency_limit * 60 * 60:
            os.remove(path)
            async with self._mutex:
                api.weather.clear()

    async def update_weather_data(self) -> None:
        self.logger.debug("Trying to update weather data")
        if not await is_connected():
            self.logger.error(
                "Ouranos is not connected to the internet, could not update "
                "weather data"
            )
            await self.clear_old_weather_data()
            return
        try:
            url = (
                f"https://api.darksky.net/forecast/{self._API_key}/"
                f"{self._coordinates[0]},{self._coordinates[1]}"
            )
            parameters = {
                "exclude": ["minutely", "alerts", "flags"],
                "units": "ca",  # ca: SI units with speed in km/h rather than m/s
            }
            async with ClientSession() as session:
                async with session.get(url, params=parameters, timeout=3.0) as resp:
                    raw_data = await resp.json()
        except ClientError:
            self.logger.error("ConnectionError: cannot update weather data")
            await self.clear_old_weather_data()
        else:
            raw_data = {
                "currently": raw_data["currently"],
                "hourly": raw_data["hourly"]["data"],
                "daily": raw_data["daily"]["data"]
            }
            data = format_weather_data(raw_data)
            try:
                stringified_data = json.dumps(data).decode("utf8")
                cache_dir = current_app.cache_dir
                async with aiofiles.open(cache_dir/_weather_file, "w") as file:
                    await file.write(stringified_data)
            except Exception as e:
                self.logger.warning("Could not dump updated weather data")
            api.weather.update(data)
            await self.dispatch_weather_data()
            self.logger.debug("Weather data updated")

    async def dispatch_weather_data(self):
        now = datetime.now()
        await self.dispatcher.emit(
            "application", "weather_current",
            data={"currently": api.weather.get("currently")},
        )
        if now.minute % 15 == 0:
            await self.dispatcher.emit(
                "application", "weather_hourly",
                data={"hourly": api.weather.get("hourly")},
            )
        if now.hour % 1 == 0 and now.minute == 0:
            await self.dispatcher.emit(
                "application", "weather_daily",
                data={"daily": api.weather.get("daily")},
            )

    """Sun times"""
    async def _check_sun_times_recency(self) -> bool:
        path = current_app.cache_dir/_sun_times_file
        try:
            update_epoch = path.stat().st_ctime
        except FileNotFoundError:
            return False

        update_dt = datetime.fromtimestamp(update_epoch)
        if update_dt.date() < date.today():
            return False

        async with aiofiles.open(path, "r") as file:
            data_raw = await file.read()
        data = json.loads(data_raw)
        api.sun_times.update(data)
        self.logger.debug("Sun times data already up to date")
        return True

    async def update_sun_times_data(self):
        self.logger.debug("Updating sun times")
        if not await is_connected():
            async with self._mutex:
                api.sun_times.clear()
                self.logger.error(
                    "Ouranos is not connected to the internet, could not "
                    "update sun times data"
                )
            return
        try:
            url = "https://api.sunrise-sunset.org/json/"
            parameters = {
                "lat": self._coordinates[0],
                "lng": self._coordinates[1],
            }
            async with ClientSession() as session:
                async with session.get(url, params=parameters, timeout=3.0) as resp:
                    raw_data = await resp.json()
        except ClientError:
            self.logger.error("ConnectionError: cannot update sun times data")
            api.sun_times.clear()
        else:
            path = current_app.cache_dir/_sun_times_file
            raw_data = raw_data["results"]
            stringified_data = json.dumps(raw_data).decode("utf8")
            async with aiofiles.open(path, "w") as file:
                await file.write(stringified_data)
            formatted_data = format_sun_times_data(raw_data)
            async with self._mutex:
                api.sun_times.update(formatted_data)
            try:
                await self.dispatcher.emit(
                    "application", "sun_times", data=formatted_data
                )
            except AttributeError as e:
                # Discard error when SocketIO has not started yet
                if "NoneType" not in e.args[0]:
                    raise e
            self.logger.debug("Sun times data updated")

    async def _start(self) -> None:
        weather_delay = current_app.config.get("WEATHER_UPDATE_PERIOD")
        if all((self._API_key, self._coordinates, weather_delay)):
            if not await self._check_weather_recency():
                await self.update_weather_data()
            scheduler.add_job(
                self.update_weather_data,
                "cron", minute=f"*/{weather_delay}", misfire_grace_time=5 * 60,
                id="weather"
            )
        if self._coordinates is not None:
            if not await self._check_sun_times_recency():
                await self.update_sun_times_data()
            scheduler.add_job(
                self.update_sun_times_data,
                "cron", hour="1", misfire_grace_time=15 * 60,
                id="suntimes"
            )

    def start(self) -> None:
        asyncio.ensure_future(self._start())

    def stop(self) -> None:
        scheduler.remove_job("weather")
        scheduler.remove_job("suntimes")
        api.weather.clear()


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

current_and_daily = {**info}.update({
    "sun_times": {
        "sunrise": 1,
        "sunset": 1,
        "moonrise": 1,
        "moonset": 1,
    }
})
