from collections.abc import MutableMapping
import logging

from cachetools import Cache, TTLCache
from redis import Redis, RedisError
from werkzeug.local import LocalProxy

from app.cache import redisCache, redisTTLCache


_CACHES_CLASS_AVAILABLE = [Cache, TTLCache, redisCache, redisTTLCache]

WEATHER_MEASURES = {
    "mean": ["temperature", "temperatureLow", "temperatureHigh", "humidity",
             "windSpeed", "cloudCover", "precipProbability", "dewPoint"],
    "mode": ["summary", "icon"],
    "other": ["time", "sunriseTime", "sunsetTime"],
}

WEATHER_DATA_MULTIPLICATION_FACTORS = {
    "temperature": 1,
    "humidity": 100,
    "windSpeed": 1,
    "cloudCover": 100,
    "precipProbability": 100,
}

rd = None

status = False
_redis_status = False


_caches = {
    "sensorsData": {},
    "healthData": {},
    "systemData": {},
    "weatherData": {},
}


def update_redis_status(config_class):
    global _redis_status
    logger = logging.getLogger(config_class.APP_NAME)
    if config_class.USE_REDIS_CACHE:
        try:
            rd.ping()
            _redis_status = True
            logger.debug(
                "Successful connection to Redis server, Redis will be used "
                "to provide data cache")
        except RedisError:
            _redis_status = False
            logger.warning(
                "Failed to connect to Redis server, using 'cachetools' to "
                "provide data cache")


def _setup_cache(cache_name, ttl=None, maxsize=16) -> MutableMapping:
    if _redis_status:
        if not ttl:
            return redisCache(cache_name, rd, check_client=False)
        return redisTTLCache(cache_name, rd, ttl, check_client=False)
    if not ttl:
        cache = Cache(maxsize=maxsize)
        cache.name = cache_name
        return cache
    cache = TTLCache(maxsize=maxsize, ttl=ttl)
    cache.name = cache_name
    return cache


def create_cache(cache_name, ttl=None, maxsize=16, overwrite=False):
    if _caches.get(cache_name) and not overwrite:
        raise ValueError(f"The cache {cache_name} already exists")
    cache = _setup_cache(cache_name, ttl, maxsize)
    _caches[cache_name] = cache
    return cache


def get_cache(cache_name):
    if not status:
        raise RuntimeError(f"Please start dataspace before accessing {cache_name}")
    try:
        return _caches[cache_name]
    except KeyError:
        raise ValueError(f"No cache named {cache_name} available")


def caches_available() -> list:
    return [cache for cache in _caches]


def clean_caches():
    if _redis_status:
        # Remove unnecessary data
        for cache in _caches:
            try:
                _caches[cache].clean()
            except AttributeError:  # The cache is not a redisCache
                pass


def init(config_class):
    global rd
    rd = Redis.from_url(config_class.REDIS_URL)
    reset(config_class)
    global status
    status = True


def reset(config_class):
    update_redis_status(config_class)
    create_cache("sensorsData", ttl=config_class.GAIA_ECOSYSTEM_TIMEOUT,
                 maxsize=config_class.GAIA_MAX_ECOSYSTEMS, overwrite=True)
    create_cache("healthData", ttl=60*60*36,
                 maxsize=config_class.GAIA_MAX_ECOSYSTEMS, overwrite=True)
    create_cache("systemData", ttl=60 * 2, maxsize=2, overwrite=True)


# Potentially workers-shared caches
sensorsData = LocalProxy(lambda: get_cache("sensorsData"))
healthData = LocalProxy(lambda: get_cache("healthData"))
systemData = LocalProxy(lambda: get_cache("systemData"))
# TODO: weather cache based on file (save 2 files: raw_data and data)
weatherData = LocalProxy(lambda: get_cache("weatherData"))


# Workers-specific caches
sensorsDataHistory = TTLCache(maxsize=32, ttl=15 * 60)
