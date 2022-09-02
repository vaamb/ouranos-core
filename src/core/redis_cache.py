from collections import deque
from collections.abc import MutableMapping
import time
import typing as t

from src.utils import json


class RedisCache(MutableMapping):
    """A cache using a redis server as backend

    """
    def __init__(self, name: str, redis_client, *args, **kwargs):
        self._name = name
        self._key_store = deque()
        self._client = redis_client
        self.clear()

    def __repr__(self):
        items = self._client.hgetall(self._name)
        decoded_items = {
            k.decode(): json.loads(v.decode()) for k, v in items.items()
        }
        return (
            f"{self.__class__.__name__}({decoded_items}, name={self._name})"
        )

    def __setitem__(self, key, value) -> None:
        self._client.hset(self._name, key, json.dumps(value))

    def __getitem__(self, key):
        value = self._client.hget(self._name, key)
        if value is None:
            raise KeyError(key)
        return json.loads(value.decode())

    def __delitem__(self, key) -> None:
        rv = self._client.hdel(self._name, key)
        if rv == 0:
            raise KeyError(key)

    def __len__(self) -> int:
        return self._client.hlen(self._name)

    def __iter__(self) -> t.Iterator:
        # works but inefficient
        mem_cached = self._client.hgetall(self._name)
        for key in mem_cached:
            yield key.decode()

    def __del__(self) -> None:
        self.clear()

    def clear(self) -> None:
        all_keys = self._client.hgetall(self._name).keys()
        if all_keys:
            self._client.hdel(self._name, *all_keys)


class RedisTTLCache(RedisCache):
    def __init__(
            self,
            name: str,
            ttl: int,
            redis_client,
            *args,
            **kwargs
    ) -> None:
        super().__init__(name, redis_client, args, **kwargs)
        self._ttl = ttl

    def __repr__(self):
        self.expire()
        items = self._client.hgetall(self._name)
        decoded_items = {
            k.decode(): json.loads(v.decode())["data"] for k, v in items.items()
        }
        return (
            f"{self.__class__.__name__}({decoded_items}, name={self._name}, "
            f"ttl={self._ttl})"
        )

    def __setitem__(self, key, value):
        expire = time.monotonic() + self._ttl
        payload = {"exp": expire, "data": value}
        super().__setitem__(key, payload)

    def __getitem__(self, key):
        payload = super().__getitem__(key)
        if time.monotonic() > payload["exp"]:
            self._client.hdel(self._name, key)
            raise KeyError(key)
        return payload["data"]

    def __len__(self) -> int:
        self.expire()
        return super().__len__()

    def __iter__(self):
        self.expire()
        return super().__iter__()

    def expire(self):
        """Loop through keys to remove expired ones"""
        mtime = time.monotonic()
        items = self._client.hgetall(self._name).items()
        to_delete = [key for (key, value) in items if
                     mtime > json.loads(value.decode())["exp"]]
        if to_delete:
            self._client.hdel(self._name, *to_delete)
