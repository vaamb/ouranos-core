from __future__ import annotations

from collections.abc import MutableMapping
import logging

from cachetools import Cache, TTLCache

from .redis_cache import RedisCache, RedisTTLCache
from ouranos import current_app

try:
    import redis
except ImportError:
    redis = None


_CACHE_CREATED: bool = False
_CACHING_SERVER_REACHABLE: int = 2
CACHE_WEATHER_DATA: bool = False
CACHING_SERVER_URL: str = ""

_CACHE_TTL_INFO: dict[str, int] = {
    "sensors_data": current_app.config["ECOSYSTEM_TIMEOUT"],
    "system_data": 90,
    "weather_data": 0,
    "sun_times_data": 0,
}

_store: dict[str, MutableMapping] = {}

logger: logging.Logger = logging.getLogger("ouranos.cache_factory")


def _create_cache(
        cache_name: str,
        config: dict,
) -> MutableMapping:
    global _CACHE_CREATED, _CACHING_SERVER_REACHABLE
    _CACHE_CREATED = True
    url = config.get("CACHING_SERVER_URL", "")
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
            if _CACHE_TTL_INFO[cache_name] > 0:
                return RedisTTLCache(cache_name, _CACHE_TTL_INFO[cache_name], _redis)
            else:
                return RedisCache(cache_name, _redis)
    elif _CACHE_TTL_INFO[cache_name] > 0:
        return TTLCache(maxsize=32, ttl=_CACHE_TTL_INFO[cache_name])
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
