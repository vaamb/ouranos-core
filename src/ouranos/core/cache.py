from __future__ import annotations

from collections.abc import MutableMapping
from enum import IntEnum
import logging

from cachetools import Cache, TTLCache

from .redis_cache import RedisCache, RedisTTLCache
from ouranos import current_app


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

    url = config.get("CACHING_SERVER_URL", "")
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
                        "Cannot connect to Redis server, using base dispatcher "
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
