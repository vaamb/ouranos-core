from collections.abc import Mapping, MutableMapping
import datetime
import json
import time

from tzlocal import get_localzone


localTZ = get_localzone()


TTL_INFO_ERROR = json.decoder.JSONDecodeError


def _str_to_bool(string):
    if string == "True":
        return True
    return False


def _dumps_dt(obj) -> str:
    if isinstance(obj, (datetime.datetime, datetime.date)):
        obj = obj.astimezone(tz=datetime.timezone.utc)
        return obj.replace(microsecond=0).isoformat()
    if isinstance(obj, datetime.time):
        obj = datetime.datetime.combine(datetime.date.today(), obj)
        obj = obj.astimezone(tz=localTZ)
        obj = obj.astimezone(tz=datetime.timezone.utc).time()
        return obj.replace(microsecond=0).isoformat()


class redisCache(MutableMapping):
    """Dict-like object to access Redis-stored data. """
    def __init__(self, name, redis_client, check_client=True, *args, **kwargs):
        if check_client:
            if not redis_client.ping():
                raise RuntimeError(
                    f"Redis server could not be contacted, unable to "
                    f"instantiate {self.__class__.__name__}"
                )
        if self.__class__.__name__ in ("redisCache", "hybridCache"):
            kwargs.pop("ttl", None)
        self._name = name
        self._redis_client = redis_client
        self._check_ttl_info(ttl="ttl" in kwargs)

    def __setitem__(self, key, value):
        self._redis_client.hset(self._name, key, self._encode_value(value))

    def __getitem__(self, key):
        value = self._redis_client.hget(self._name, key)
        if value is None:
            if not self._redis_client.hexists(self._name, key):
                self.__missing__(key)
        data = self._decode_byte_value(key, value)
        return data

    def __delitem__(self, key):
        # Rem: does not check if key exists before removing element in order
        # to reduce IO. Use .delete() if you want to raise KeyError if the key
        # is not present in Redis server
        self._redis_client.hdel(self._name, key)

    def __len__(self):
        return self._redis_client.hlen(self._name)

    def __iter__(self):
        data = self._redis_client.hgetall(self._name)
        return iter({key.decode(): data[key] for key in data
                     if key != b"ttl_info"})

    def __missing__(self, key):
        raise KeyError(key)

    def __repr__(self):
        return f"{self.__class__.__name__}({self.items()})"

    def _check_ttl_info(self, ttl):
        # TTL code: 0: empty cache, 1: was not using ttl, 2: was using ttl
        last_ttl = self._redis_client.hget(self._name, "ttl_info")
        if last_ttl is None:
            if ttl:
                self._redis_client.hset(self._name, "ttl_info", "True")
            else:
                self._redis_client.hset(self._name, "ttl_info", "False")
            return
        last_ttl = _str_to_bool(last_ttl)
        if last_ttl:
            if not ttl:
                raise TypeError(
                    f"There already is a redisDict named '{self._name}' "
                    f"configured with ttl. Either use it by using a "
                    f"redisTTLCache or override it with redisCache.override()"
                )
        else:
            if ttl:
                raise TypeError(
                    f"There already is a redisDict named '{self._name}' "
                    f"configured without ttl. Either use it by using a "
                    f"redisCache or override it with redisTTLCache.override()"
                )

    def _decode_byte_value(self, key, value):
        try:
            return json.loads(value)
        except TypeError:
            return value
        except TTL_INFO_ERROR:
            return _str_to_bool(value.decode('utf-8'))

    def _encode_value(self, value):
        if isinstance(value, bytes):
            raise TypeError("redisDict cannot store bytes object")
        return json.dumps(value, default=_dumps_dt)

    def items(self):
        return [(key, self[key]) for key in self]

    def update(self, *args, **kwargs):
        if len(args) > 1:
            raise TypeError(f"update expected at most 1 arguments, got "
                            f"{len(args)}")
        items = {}
        obj = args[0]
        if isinstance(obj, Mapping):
            items.update({key: self._encode_value(obj[key]) for key in obj})
        items.update({key: self._encode_value(obj[key]) for key in kwargs})
        self._redis_client.hset(self._name, mapping=items)

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default

    def pop(self, key, *args):
        try:
            value = self[key]
            del self[key]
            return value
        except KeyError:
            if len(args) == 0:
                self.__missing__(key)
            elif len(args) == 1:
                return args[0]
            else:
                raise TypeError("pop() takes maximum one argument")

    def clean(self):
        # Clean Redis data when finish app cleanly
        key_list = [key for key in self]
        for key in key_list:
            del self[key]
        del self["ttl_info"]

    def delete(self, *keys):
        for key in keys:
            if not self._redis_client.hexists(self._name, key):
                self.__missing__(key)
            del self[key]

    @classmethod
    def override(cls, name, redis_client, *args, **kwargs):
        keys = redis_client.hkeys(name)
        redis_client.hdel(name, *keys)
        return cls(name, redis_client, *args, **kwargs)

    @property
    def name(self):
        return self._name

    @property
    def ttl(self):
        return None

    @property
    def grace_time(self):
        return None


class redisTTLCache(redisCache):
    """Dict-like object to access Redis-stored data. """
    def __init__(self, name, redis_client, ttl, *args, **kwargs):
        assert ttl > 0
        kwargs.update(ttl=ttl)
        super().__init__(name, redis_client, *args, **kwargs)
        self._ttl = ttl

    def __iter__(self):
        data = self._redis_client.hgetall(self._name)
        results = {}
        for key in data:
            dkey = key.decode("utf8")
            try:
                value = json.loads(data[key])
                if value["ttl"] >= time.time():
                    results.update({dkey: value["data"]})
                else:
                    del self[key]
            except TTL_INFO_ERROR:
                # Getting ttl_info value
                continue
        return iter(results)

    def __repr__(self):
        return f"{self.__class__.__name__}({self.items()}, ttl={self.ttl})"

    def _decode_byte_value(self, key, value):
        try:
            data = json.loads(value)
        except TypeError:
            # Got a None
            return value
        except TTL_INFO_ERROR:
            return _str_to_bool(value.decode('utf-8'))

        if data["ttl"] >= time.time():
            return data["data"]
        else:
            del self[key]
            self.__missing__(key)

    def _encode_value(self, value):
        if isinstance(value, bytes):
            raise TypeError("redisDict cannot store bytes object")
        ttl = time.time() + self._ttl
        data = {"data": value, "ttl": ttl}
        return json.dumps(data, default=_dumps_dt)

    @property
    def ttl(self):
        return self._ttl


class hybridCache(redisCache):
    def __init__(self, name, redis_client, grace_time=2, *args, **kwargs):
        super().__init__(name, redis_client)
        self._grace_time = grace_time
        self._store = dict()

    def __getitem__(self, key):
        try:
            if self._store[key]["ttl"] > time.monotonic():
                return self._store[key]["data"]
            else:
                del self._store[key]
        except KeyError:
            pass
        value = self._redis_client.hget(self._name, key)
        if value is None:
            if not self._redis_client.hexists(self._name, key):
                self.__missing__(key)
        data = self._decode_byte_value(key, value)
        self._store[key] = {"ttl": time.monotonic() + self._grace_time,
                            "data": data}
        return data

    def __repr__(self):
        return f"{self.__class__.__name__}({self.items()}, " \
               f"grace_time={self.grace_time})"

    @property
    def grace_time(self):
        return self._grace_time

    @grace_time.setter
    def grace_time(self, grace_time):
        self._grace_time = grace_time


class hybridTTLCache(redisTTLCache, hybridCache):
    def __init__(self, name, redis_client, ttl, grace_time=2):
        super().__init__(name, redis_client, ttl, grace_time=grace_time)

    def __repr__(self):
        return f"{self.__class__.__name__}({self.items()}, ttl={self.ttl}, " \
               f"grace_time={self.grace_time})"


__all__ = "redisCache", "redisTTLCache", "hybridCache", "hybridTTLCache"
