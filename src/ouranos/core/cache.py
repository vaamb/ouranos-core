from __future__ import annotations

from collections.abc import MutableMapping
from enum import IntEnum
import logging

from cachetools import Cache, TTLCache

from ouranos import current_app
from ouranos.core.redis_cache import RedisCache, RedisTTLCache


class SERVER_STATUS(IntEnum):
    NOT_CONNECTED = 0
    CONNECTED = 1
    UNKNOWN = 2


_state: dict = {"server_status": SERVER_STATUS.UNKNOWN}
_store: dict[str, MutableMapping] = {}


logger: logging.Logger = logging.getLogger("ouranos.cache_factory")


def _create_cache(
        cache_name: str,
        config: dict,
) -> MutableMapping:
    CACHE_TTL_INFO: dict[str, int] = {
        "sensors_data": current_app.config["ECOSYSTEM_TIMEOUT"],
        "system_data": 90,
        "weather_data": 0,
        "sun_times_data": 0,
    }

    url = config.get("CACHE_SERVER_URL", "")
    if url.startswith("redis"):
        try:
            import redis
        except ImportError:
            raise RuntimeError(
                "redis package with hiredis is required. Run "
                "`pip install redis[hiredis]` in your virtual "
                "env."
            )
        else:
            _redis = redis.Redis.from_url(url)
            if _state["server_status"] == SERVER_STATUS.UNKNOWN:
                try:
                    _redis.ping()
                    _state["server_status"] = SERVER_STATUS.CONNECTED
                except redis.RedisError:
                    logger.warning(
                        "Cannot connect to Redis server, using Base dispatcher "
                        "instead."
                    )
                    _state["server_status"] = SERVER_STATUS.NOT_CONNECTED
            if _state["server_status"] == SERVER_STATUS.CONNECTED:
                if CACHE_TTL_INFO[cache_name] > 0:
                    return RedisTTLCache(
                        cache_name, CACHE_TTL_INFO[cache_name], _redis
                    )
                else:
                    return RedisCache(cache_name, _redis)
    elif CACHE_TTL_INFO[cache_name] > 0:
        return TTLCache(maxsize=32, ttl=CACHE_TTL_INFO[cache_name])
    return Cache(maxsize=32)


def get_cache(
        cache_name: str,
        config: dict | None = None,
) -> MutableMapping:
    config = config or current_app.config
    if not config:
        raise RuntimeError(
            "Either provide a config dict or set config globally with "
            "g.set_app_config"
        )
    global _store
    try:
        return _store[cache_name]
    except KeyError:
        cache = _create_cache(cache_name, config)
        _store[cache_name] = cache
        return cache


class DataCache:
    @classmethod
    def _get_cache(cls) -> MutableMapping:
        raise NotImplemented

    @classmethod
    def get(cls) -> MutableMapping:
        return cls._get_cache()

    @classmethod
    def update(cls, data: dict) -> None:
        cache = cls._get_cache()
        cache.update(data)

    @classmethod
    def clear(cls, key: str | None = None) -> None:
        cache = cls._get_cache()
        if key:
            del cache[key]
        else:
            cache.clear()


class WeatherCache(DataCache):
    @classmethod
    def _get_cache(cls):
        return get_cache("weather_data")

    @classmethod
    def get_currently(cls) -> dict:
        cache = cls._get_cache()
        return cache.get("currently", {})

    @classmethod
    # Weather forecast
    def _get_forecast(cls, time_unit: str, time_window: int) -> dict:
        cache = cls._get_cache()
        data = cache.get(time_unit)
        if data:
            if time_window > len(data["forecast"]):
                time_window = len(data["forecast"]) - 1
            forecast = [data["forecast"][_] for _ in range(time_window)]
            return {
                "time_window": {
                    "start": forecast[0]["time"],
                    "end": forecast[time_window - 1]["time"]
                },
                "forecast": forecast,
            }
        return {}

    @classmethod
    def get_hourly(cls, time_window: int = 24) -> dict:
        return cls._get_forecast("hourly", time_window)

    @classmethod
    def get_daily(
            cls,
            time_window: int = 7,
            skip_today: bool = True
    ) -> dict:
        data = cls._get_forecast("daily", time_window)
        if not data:
            return {}
        if skip_today:
            del data["forecast"][0]
        return data


class SunTimesCache(DataCache):
    @classmethod
    def _get_cache(cls):
        return get_cache("sun_times_data")


"""
def summarize_forecast(forecast: dict) -> dict:
    digest: dict[str, list] = {}
    data = forecast["forecast"]
    for elem in data:
        for info in WEATHER_MEASURES["mode"] + WEATHER_MEASURES["mean"]:
            try:
                d = elem[info]
            except KeyError:
                continue
            else:
                try:
                    digest[info].append(d)
                except KeyError:
                    digest[info] = [d]

    result = {}
    for info in digest:
        if info in WEATHER_MEASURES["mode"]:
            result[info] = mode(digest[info])
        elif info in WEATHER_MEASURES["mean"]:
            result[info] = mean(digest[info])
        if info in WEATHER_MEASURES["range"]:
            result[f"{info}High"] = max(digest[info])
            result[f"{info}Low"] = min(digest[info])

    return {
        "time_window": forecast["time_window"],
        "forecast": result,
    }


def _digest_hourly_weather_forecast(weather_forecast: dict) -> dict:
    if weather_forecast:
        now = datetime.now(timezone.utc)
        digest = {}
        for hour in weather_forecast["forecast"]:
            tod = _get_time_of_day(hour["datetime"].time())
            time_limits = {
                "today": now.date(),
                "tomorrow": now.date() + timedelta(days=1),
                "day_after_tomorrow": now.date() + timedelta(days=2),
            }
            for time_limit in time_limits:
                if hour["datetime"].date() == time_limits[time_limit]:
                    day = time_limit
                    try:
                        digest[day]
                    except KeyError:
                        digest[day] = {}
                    break

            try:
                digest[day][tod]
            except KeyError:
                digest[day][tod] = {}

            for info in WEATHER_MEASURES["mean"] + WEATHER_MEASURES["mode"]:
                try:
                    digest[day][tod][info].append(hour["weather"][info])
                except KeyError:
                    digest[day][tod].update({info: [hour["weather"][info]]})

        return {
            "time_window": weather_forecast["time_window"],
            "forecast": digest,
        }
    return {}


def _summarize_digested_weather_forecast(digested_weather_forecast: dict) -> dict:
    if digested_weather_forecast:
        summary = {
            "time_window": digested_weather_forecast["time_window"],
            "forecast": {}
        }

        for day in digested_weather_forecast["forecast"]:
            day_forecast = digested_weather_forecast["forecast"][day]
            summary["forecast"][day] = {}

            for tod in day_forecast:
                summary["forecast"][day][tod] = {}

                for info in WEATHER_MEASURES["mode"]:
                    summary["forecast"][day][tod][info] = \
                        mode(day_forecast[tod][info])[0]

                for info in WEATHER_MEASURES["mean"]:
                    summary["forecast"][day][tod][info] = \
                        round(mean(day_forecast[tod][info]), 1)

        return digested_weather_forecast
    return {}


def get_digested_hourly_weather_forecast(time_window: int = 24) -> dict:
    forecast = weather.get_hourly(time_window=time_window)
    digest = _digest_hourly_weather_forecast(forecast)
    summary = _summarize_digested_weather_forecast(digest)
    return summary
"""
