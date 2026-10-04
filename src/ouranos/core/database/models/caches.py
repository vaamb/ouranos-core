from typing import Any, Hashable

from cachetools import LRUCache, TTLCache


_CT = TTLCache[tuple[Hashable, ...], Any]


# App
cache_users = LRUCache(maxsize=32)
cache_services: _CT = TTLCache(maxsize=16, ttl=60)


# Gaia
# Caches size
_engine_caches_size = 4
_ecosystem_caches_size = _engine_caches_size * 2
_hardware_caches_size = _ecosystem_caches_size * 8
_system_cache_size = 2
# Engine caches
cache_engines = LRUCache(maxsize=_engine_caches_size)
cache_engines_recent: TTLCache[str, Any] = TTLCache(maxsize=1, ttl=30)
# Ecosystem caches
cache_ecosystems = LRUCache(maxsize=_ecosystem_caches_size)
cache_ecosystems_recent: TTLCache[str, Any] = TTLCache(maxsize=1, ttl=30)
cache_ecosystems_has_recent_data: _CT = TTLCache(maxsize=_ecosystem_caches_size * 2, ttl=60)
cache_ecosystems_has_recent_picture: _CT = TTLCache(maxsize=_ecosystem_caches_size, ttl=60)
cache_ecosystems_has_active_actuator: _CT = TTLCache(maxsize=_ecosystem_caches_size, ttl=60)
# Hardware caches
cache_hardware = LRUCache(maxsize=_hardware_caches_size)
cache_hardware_groups = LRUCache(maxsize=_hardware_caches_size)
# Sensor caches
cache_sensors_data_skeleton: _CT = TTLCache(maxsize=_ecosystem_caches_size * 3, ttl=900)
cache_sensors_value: _CT = TTLCache(maxsize=_ecosystem_caches_size * 32, ttl=600)
# Measure caches
cache_measures = LRUCache(maxsize=16)
# Plant caches
cache_plants = LRUCache(maxsize=_hardware_caches_size)
# Warning caches
cache_warnings: _CT = TTLCache(maxsize=5, ttl=60)


# System
cache_systems = LRUCache(maxsize=_system_cache_size)
cache_systems_history: _CT = TTLCache(maxsize=_system_cache_size, ttl=60*5)
