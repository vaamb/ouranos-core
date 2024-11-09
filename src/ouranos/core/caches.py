from __future__ import annotations

from pathlib import Path
import pickle
from typing import Any, Iterable

import aiosqlite

from ouranos import current_app

_create_query = """
  CREATE TABLE IF NOT EXISTS %(table_name)s (
    key TEXT UNIQUE NOT NULL,
    value BLOB NOT NULL,
    ttl TIMESTAMP DEFAULT CURRENT_TIMESTAMP
  )
"""
_get_query = "SELECT value FROM %(table_name)s WHERE key = CAST(? AS TEXT)"
_set_query = "REPLACE INTO %(table_name)s (key, value) VALUES (CAST(? AS TEXT), CAST(? AS BLOB))"
_delete_query = "DELETE FROM %(table_name)s WHERE key = CAST(? AS TEXT)"
_delete_all_query = "DELETE FROM %(table_name)s"
_iter_query = "SELECT key FROM %(table_name)s"


class aioCache:
    def __init__(self, file_path: Path | str, table: str = "cache") -> None:
        self._path = Path(file_path)
        self._table = table
        self._init: bool = False

    @property
    def is_init(self) -> bool:
        return self._init

    def _check_init(self) -> None:
        if not self.is_init:
            raise RuntimeError("Cache is not initialized")

    async def init(self):
        async with aiosqlite.connect(self._path) as db:
            await db.execute(_create_query % {"table_name": self._table})
            await db.commit()
        self._init = True

    async def get(self, key: str) -> Any:
        self._check_init()
        async with aiosqlite.connect(self._path) as db:
            cursor = await db.execute(_get_query % {"table_name": self._table}, (key,))
            row = await cursor.fetchone()
        if not row:
            raise KeyError(key)
        return pickle.loads(row[0])

    async def set(self, key: str, value: Any) -> None:
        # Set is inefficient
        self._check_init()
        value = pickle.dumps(value)
        async with aiosqlite.connect(self._path) as db:
            await db.execute(_set_query % {"table_name": self._table}, (key, value))
            await db.commit()

    async def delete(self, key: str) -> None:
        self._check_init()
        async with aiosqlite.connect(self._path) as db:
            cursor = await db.execute(_delete_query % {"table_name": self._table}, (key,))
            if not cursor.rowcount:
                raise KeyError(key)
            await db.commit()

    async def clear(self) -> None:
        self._check_init()
        async with aiosqlite.connect(self._path) as db:
            await db.execute(_delete_all_query % {"table_name": self._table})
            await db.commit()

    async def keys(self) -> Iterable[str]:
        self._check_init()
        async with aiosqlite.connect(self._path) as db:
            cursor = await db.execute(_iter_query % {"table_name": self._table})
            rows = await cursor.fetchall()
            for row in rows:
                yield row[0]


class CacheFactory:
    __caches: dict[str, aioCache] = {}
    __config: dict[str, Any] = {
        "sky_watcher": {
            "cache_path": "sky_watcher.sqlite",
        },
    }

    @classmethod
    def update_config(cls, cfg: dict[str, Any]) -> None:
        cls.__config.update(cfg)

    @classmethod
    def get(
            cls,
            name: str,
    ) -> aioCache:
        try:
            return cls.__caches[name]
        except KeyError:
            try:
                cache_path_str = cls.__config[name]["cache_path"]
            except KeyError:
                raise ValueError(f"Cache '{name}' does not have a valid config")
            cache_path = current_app.cache_dir / cache_path_str
            table_name = cls.__config[name].get("table_name", "cache")


            cache = aioCache(cache_path, table_name)
            cls.__caches[name] = cache
            return cache
