from datetime import datetime, timezone
import logging
from typing import Union

from cachetools import Cache, TTLCache
from redis import Redis, RedisError
from werkzeug.local import LocalProxy

from config import Config  # For type hint only
from src.dataspace.dispatcher import BaseDispatcher, PubSubDispatcher, RedisDispatcher
from src.dataspace.pubsub import StupidPubSub


STOP_SIGNAL = "__STOP__"

START_TIME = datetime.now(timezone.utc).replace(microsecond=0)

WEATHER_MEASURES = {
    "mean": ["temperature", "temperatureLow", "temperatureHigh", "humidity",
             "windSpeed", "cloudCover", "precipProbability", "dewPoint"],
    "mode": ["summary", "icon", "sunriseTime", "sunsetTime"],
    "other": ["time", "sunriseTime", "sunsetTime"],
    "range": ["temperature"],
}

WEATHER_DATA_MULTIPLICATION_FACTORS = {
    "temperature": 1,
    "humidity": 100,
    "windSpeed": 1,
    "cloudCover": 100,
    "precipProbability": 100,
}

_caches = {
    "sensorsData": Cache,
    "healthData": Cache,
    "systemData": Cache,
    "weatherData": {},
    "sunTimesData": {},
}

_dispatchers = {}

_store = {}


def _check_init():
    if not _store.get("initialized"):
        raise RuntimeError("Please use 'dataspace.init(Config)' before")


def _get_redis() -> Redis:
    _check_init()
    try:
        return _store["redis"]
    except KeyError:
        cfg = _store["config"]
        logger = logging.getLogger(cfg.APP_NAME)
        rd = Redis.from_url(cfg.REDIS_URL)
        if cfg.USE_REDIS_CACHE or cfg.USE_REDIS_DISPATCHER:
            try:
                rd.ping()
                logger.debug(
                    "Successful connection to Redis server, Redis will be used "
                    "to provide data cache"
                )
                _store["redis"] = rd
            except RedisError:
                logger.warning(
                    "Failed to connect to Redis server, using 'cachetools' to "
                    "provide data cache"
                    # TODO: say won't work when using several instances
                )
                _store["redis"] = None
        else:
            _store["redis"] = None
    return _store["redis"]


def create_cache(cache_name: str,
                 maxsize: int = 16,
                 ttl: int = None,
                 overwrite: bool = False) -> Cache:
    _check_init()
    if _caches.get(cache_name) and not overwrite:
        raise ValueError(f"The cache {cache_name} already exists")
    if not ttl:
        cache = Cache(maxsize=maxsize)
    else:
        cache = TTLCache(maxsize=maxsize, ttl=ttl)
    _caches[cache_name] = cache
    return cache


def get_cache(cache_name: str) -> Union[Cache, dict]:
    _check_init()
    try:
        return _caches[cache_name]
    except KeyError:
        raise ValueError(f"No cache named {cache_name} available")


def caches_available() -> list:
    return [cache for cache in _caches]


def get_dispatcher(name: str) -> BaseDispatcher:
    _check_init()
    try:
        return _dispatchers[name]
    except KeyError:
        rd = redis
        cfg = _store["config"]
        if rd and cfg.USE_REDIS_DISPATCHER:
            _dispatcher = RedisDispatcher(name, rd)
            _dispatchers[name] = _dispatcher
        else:
            _pubsub = StupidPubSub()
            _dispatcher = PubSubDispatcher(name, _pubsub)
            _dispatchers[name] = _dispatcher
        return _dispatcher


def init(config_class: Config) -> None:
    if not _store.get("initialized"):
        _store["initialized"] = True
        _store["config"] = config_class
        reset()


def reset() -> None:
    # TODO: reset all dicts, including _dispatcher
    cfg = _store["config"]
    create_cache("sensorsData", ttl=cfg.GAIA_ECOSYSTEM_TIMEOUT,
                 maxsize=cfg.GAIA_MAX_ECOSYSTEMS, overwrite=True)
    create_cache("healthData", ttl=60*60*36,
                 maxsize=cfg.GAIA_MAX_ECOSYSTEMS, overwrite=True)
    create_cache("systemData", ttl=90,
                 maxsize=16, overwrite=True)


redis = LocalProxy(lambda: _get_redis())


# Potentially workers-shared caches
# TODO: change sensorsData to avoid confusion
sensorsData = LocalProxy(lambda: get_cache("sensorsData"))
healthData = LocalProxy(lambda: get_cache("healthData"))  # TODO: del healthData as all data points are logged
systemData = LocalProxy(lambda: get_cache("systemData"))
# TODO: weather cache based on file (save 2 files: raw_data and data)
weatherData = LocalProxy(lambda: get_cache("weatherData"))
sunTimesData = LocalProxy(lambda: get_cache("sunTimesData"))

# Workers-specific caches
