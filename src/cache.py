from collections.abc import MutableMapping
import inspect
import logging
from typing import Union, Type

from cachetools import Cache, TTLCache
from werkzeug.local import LocalProxy

try:
    import redis
except ImportError:
    redis = None

from config import Config
from .redis_cache import RedisCache, RedisTTLCache


_CACHE_CREATED: bool = False
_CACHING_SERVER_REACHABLE: int = 2
CACHE_WEATHER_DATA: bool = False
CACHING_SERVER_URL: str = ""

_CACHE_INFO: dict[str, int] = {
    "sensorsData": Config.GAIA_ECOSYSTEM_TIMEOUT,
    "systemData": 90,
    "weatherData": 0,
    "sunTimesData": 0,
}

_store: dict[str, MutableMapping] = {}

logger: logging.Logger = logging.getLogger("ouranos.cache_factory")


def _get_url(config: Union[dict, None, Type[Config]]) -> str:
    if config is None:
        return CACHING_SERVER_URL
    elif isinstance(config, dict):
        return config.get("CACHING_SERVER_URL", CACHING_SERVER_URL)
    elif inspect.isclass(config):
        return vars(config).get("CACHING_SERVER_URL", CACHING_SERVER_URL)
    else:
        raise ValueError("config must either be a class or a dict")


def configure_caches(
        config: Union[dict, None, Type[Config]],
        override: bool = False,
        silent: bool = False,
) -> None:
    global _CACHE_CREATED, _CACHING_SERVER_REACHABLE, CACHING_SERVER_URL
    if not _CACHE_CREATED or override:
        CACHING_SERVER_URL = _get_url(config)
        _CACHING_SERVER_REACHABLE = 2
    elif _CACHE_CREATED and not silent:
        logger.warning(
            "It is not recommended to configure caches once a cache has been. "
            "If you want to override this behavior, use 'override=True'."
        )


def _create_cache(
        cache_name: str,
        config: Union[dict, None, Type[Config]] = None,
) -> MutableMapping:
    global _CACHE_CREATED, _CACHING_SERVER_REACHABLE
    _CACHE_CREATED = True
    url = _get_url(config)
    if url.startswith("redis"):
        if redis is None:
            raise RuntimeError(
                "redis package with hiredis is required. Run "
                "`pip install redis[hiredis]` in your virtual "
                "env."
            )
        _redis = redis.Redis.from_url(url)
        if _CACHING_SERVER_REACHABLE == 2:
            try:
                _redis.ping()
                _CACHING_SERVER_REACHABLE = 1
            except redis.RedisError:
                logger.warning(
                    "Cannot connect to Redis server, using base dispatcher "
                    "instead."
                )
                _CACHING_SERVER_REACHABLE = 0
        if _CACHING_SERVER_REACHABLE == 1:
            if _CACHE_INFO[cache_name] > 0:
                return RedisTTLCache(cache_name, _CACHE_INFO[cache_name], _redis)
            else:
                return RedisCache(cache_name, _redis)
    if _CACHE_INFO[cache_name] > 0:
        return TTLCache(maxsize=32, ttl=_CACHE_INFO[cache_name])
    return Cache(maxsize=32)


def get_cache(
        cache_name: str,
        config: Union[dict, None, Type[Config]] = None,
) -> MutableMapping:
    global _store
    try:
        return _store[cache_name]
    except KeyError:
        cache = _create_cache(cache_name, config)
        _store[cache_name] = cache
        return cache


sensorsData = LocalProxy(lambda: get_cache("sensorsData"))
systemData = LocalProxy(lambda: get_cache("systemData"))
# TODO: weather cache based on file (save 2 files: raw_data and data)
weatherData = LocalProxy(lambda: get_cache("weatherData"))
sunTimesData = LocalProxy(lambda: get_cache("sunTimesData"))
