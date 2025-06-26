from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta
from logging import getLogger, Logger

from aiohttp import ClientError, ClientSession
from pydantic import Field, field_validator, RootModel

import gaia_validators as gv
from gaia_validators.utils import get_sun_times

from ouranos import current_app, scheduler
from ouranos.core.caches import CacheFactory
from ouranos.core.dispatchers import DispatcherFactory
from ouranos.core.utils import stripped_warning
from ouranos.core.validate.base import BaseModel


_RECENCY_LIMIT = 6 * 60 * 60


async def is_connected(ip_to_connect: str = "1.1.1.1", port: int = 80) -> bool:
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(ip_to_connect, port), 2)
        writer.close()
        return True
    except Exception as ex:
        stripped_warning(ex)
    return False


class SunTimes(RootModel):
    root: list[gv.SunTimes]


# -------------------------------------------------------------------------------
#   Weather
# -------------------------------------------------------------------------------
class WeatherDataCurrent(BaseModel):
    timestamp: datetime = Field(validation_alias="dt")
    temperature: float = Field(validation_alias="temp")
    humidity: float
    dew_point: float
    wind_speed: float
    cloud_cover: float | None = Field(validation_alias="clouds")
    summary: str | None = Field(validation_alias="weather")
    icon: str | None = Field(validation_alias="weather")

    @field_validator("timestamp", mode="before")
    def parse_timestamp(cls, value):
        if isinstance(value, int):
            return datetime.fromtimestamp(value)
        if isinstance(value, str):
            return datetime.fromisoformat(value)
        return value

    @field_validator("summary", mode="before")
    def parse_summary(cls, value):
        if not value:
            return None
        if isinstance(value, str):
            return value
        return value[0]["description"]

    @field_validator("icon", mode="before")
    def parse_icon(cls, value):
        if not value:
            return None
        if isinstance(value, str):
            return value
        return value[0]["icon"]


class WeatherDataHour(WeatherDataCurrent):
    precipitation_probability: float = Field(validation_alias="pop")


class WeatherDataDay(WeatherDataHour):
    temperature_min: float = Field(validation_alias="temp")
    temperature_max: float = Field(validation_alias="temp")

    @field_validator("temperature", mode="before")
    def parse_temperature(cls, value):
        if not value:
            return None
        if isinstance(value, float):
            return value
        return value["day"]

    @field_validator("temperature_min", mode="before")
    def parse_temperature_min(cls, value):
        if not value:
            return None
        if isinstance(value, float):
            return value
        return value["min"]

    @field_validator("temperature_max", mode="before")
    def parse_temperature_max(cls, value):
        if not value:
            return None
        if isinstance(value, float):
            return value
        return value["max"]


class WeatherData(BaseModel):
    current: WeatherDataCurrent
    hourly: list[WeatherDataHour]
    daily: list[WeatherDataDay]


async def get_weather_data(coordinates: gv.Coordinates, api_key: str) -> WeatherData:
    url = "https://api.openweathermap.org/data/3.0/onecall"
    parameters = {
        "lat": coordinates.latitude,
        "lon": coordinates.longitude,
        "appid": api_key,
        "exclude": ["minutely"],
        "units": "metric",  # ca: SI units with temperature in °C rather than °K
    }
    try:
        async with ClientSession() as session:
            async with session.get(url, params=parameters, timeout=3.0) as resp:
                raw_data = await resp.json()
                return WeatherData.model_validate(raw_data)
    except (ClientError, asyncio.TimeoutError) as e:
        raise ConnectionError from e


async def get_weather_test_data(coordinates: gv.Coordinates, api_key: str) -> WeatherData:
    base = {
        "timestamp": datetime.now(),
        "temperature": 25.0,
        "humidity": 60.0,
        "dew_point": 10.3,
        "wind_speed": 25.8,
        "cloud_cover": 82.0,
        "summary": "Cloudy",
        "icon": "02d",
    }
    return WeatherData(**{
        "current": base,
        "hourly": [{
            **base,
            "precipitation_probability": 20.0,
        }],
        "daily": [{
            **base,
            "precipitation_probability": 80.0,
            "temperature_min": 21.0,
            "temperature_max": 42.0,
        }],
    })


# -------------------------------------------------------------------------------
#   SkyWatcher class
# -------------------------------------------------------------------------------
class SkyWatcher:
    def __init__(self):
        self.logger: Logger = getLogger("ouranos.aggregator")
        self.dispatcher = DispatcherFactory.get("aggregator-internal")
        self._mutex = asyncio.Lock()
        coordinates = current_app.config.get("HOME_COORDINATES")
        if isinstance(coordinates, tuple):
            coordinates = gv.Coordinates(*coordinates)
        self._coordinates: gv.Coordinates | None = coordinates
        self._API_key = current_app.config.get("OPEN_WEATHER_MAP_API_KEY")
        self._update_period: int = current_app.config["WEATHER_UPDATE_PERIOD"]
        self._aio_cache = CacheFactory.get("sky_watcher")
        self._started: bool = False

    @property
    def started(self) -> bool:
        return self._started

    """Weather"""
    async def _check_weather_recency(self) -> bool:
        """Return True is weather data is recent (less than
        Config.WEATHER_REFRESH_INTERVAL + 1)"""

        current = await self._aio_cache.get("weather_currently", {})
        timestamp = current.get("timestamp", None)
        if timestamp is None:
            return False
        now = datetime.now()
        if now.timestamp() - timestamp.timestamp() > (self._update_period + 1) * 60 :
            self.logger.debug("Weather data already up to date")
            return True
        return False

    async def clear_old_weather_data(self) -> None:
        current = await self._aio_cache.get("weather_currently", {})
        timestamp = current.get("timestamp", None)
        if timestamp is None:
            return
        now = datetime.now()
        # If weather "current" time older than _RECENCY_LIMIT hours: clear
        if now.timestamp() - timestamp.timestamp() > _RECENCY_LIMIT:
            await self._aio_cache.delete("weather_currently")
            await self._aio_cache.delete("weather_hourly")
            await self._aio_cache.delete("weather_daily")

    async def update_weather_data(self) -> None:
        self.logger.debug("Trying to update weather data")
        if not all((self._API_key, self._coordinates)):
            self.logger.error(
                "'HOME_COORDINATES' and 'OPEN_WEATHER_MAP_API_KEY' are needed "
                "in the config class in order to update the weather forecast.")
            return
        try:
            if current_app.config["TESTING"]:
                get_weather_data = get_weather_test_data
            weather_data = await get_weather_data(self._coordinates, self._API_key)
        except ConnectionError:
            self.logger.error(
                "Ouranos is not connected to the internet, could not update "
                "weather data")
            await self.clear_old_weather_data()
            return
        else:
            # Log data in cache
            weather_data_dict = weather_data.model_dump()
            await self._aio_cache.set("weather_currently", weather_data_dict["current"])
            await self._aio_cache.set("weather_hourly", weather_data_dict["hourly"])
            await self._aio_cache.set("weather_daily", weather_data_dict["daily"])
            self.logger.debug("Weather data updated")

            # Dispatch data
            now = datetime.now()
            await self.dispatcher.emit(
                "weather_current", data=weather_data_dict["current"],
                namespace="application-internal")
            await self.dispatcher.emit(
                "weather_hourly", data=weather_data_dict["hourly"],
                namespace="application-internal")
            await self.dispatcher.emit(
                "weather_daily", data=weather_data_dict["daily"],
                namespace="application-internal")

    """Sun times"""
    async def update_sun_times_data(self) -> None:
        self.logger.debug("Updating sun times")
        today = date.today()
        days = [today + timedelta(days=i) for i in range(0, 7)]
        sun_times = [
            get_sun_times(self._coordinates, day).model_dump()
            for day in days
        ]
        await self._aio_cache.set("sun_times", sun_times)
        self.logger.debug("Sun times data updated")

    async def start(self) -> None:
        # Checks
        if self.started:
            raise RuntimeError("SkyWatcher is already started")
        if not all((self._API_key, self._coordinates)):
            self.logger.error(
                "'HOME_COORDINATES' and 'OPEN_WEATHER_MAP_API_KEY' are needed "
                "in the config class in order to use the `SkyWatcher`.")
            return
        # Start
        if not self._aio_cache.is_init:
            await self._aio_cache.init()
        tasks = []
        if not await self._check_weather_recency():
            tasks.append(self.update_weather_data())
        scheduler.add_job(
            self.update_weather_data,
            "cron", minute=f"*/{self._update_period}", misfire_grace_time=5 * 60,
            id="sky_watcher-weather",
            )
        tasks.append(self.update_sun_times_data())
        scheduler.add_job(
            self.update_sun_times_data,
            "cron", hour="0", minute="1", misfire_grace_time=15 * 60,
            id="sky_watcher-suntimes",
        )
        await asyncio.gather(*tasks)
        self._started = True

    async def stop(self) -> None:
        if not self.started:
            raise RuntimeError("SkyWatcher is not started")
        self.logger.debug("Stopping SkyWatcher")
        await self._aio_cache.clear()
        if scheduler.get_job("sky_watcher-weather"):
            scheduler.remove_job("sky_watcher-weather")
        if scheduler.get_job("sky_watcher-sun_times"):
            scheduler.remove_job("sky_watcher-sun_times")
        self._started = False
