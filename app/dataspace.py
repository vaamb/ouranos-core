from threading import Lock

from cachetools import TTLCache

from config import Config


lock = Lock()

sensorsData = TTLCache(maxsize=32, ttl=Config.ECOSYSTEM_TIMEOUT)
# TODO: use a cache which checks db if value for today present, if so load it
healthData = {}
systemData = TTLCache(maxsize=2, ttl=120)

sensorsDataHistory = TTLCache(maxsize=32, ttl=15 * 60)

__all__ = ("lock", "sensorsData", "sensorsDataHistory", "healthData", "systemData")
