import asyncio
import functools
from contextlib import AbstractContextManager
from typing import Any, Callable, MutableMapping, Optional, TypeVar

from cachetools import keys


_KT = TypeVar("_KT")


class NullContext:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        return None


def cached(
    cache: Optional[MutableMapping[_KT, Any]],
    key: Callable[..., _KT] = keys.hashkey,
    lock: Optional[AbstractContextManager[Any]] = None,
) :
    """Decorator to wrap a function with a memoizing callable that saves
    results in a cache.

    A mix from cachetools and asyncache
    """
    lock = lock or NullContext()

    def decorator(func):
        if asyncio.iscoroutinefunction(func):

            async def wrapper(*args, **kwargs):
                k = key(*args, **kwargs)
                try:
                    async with lock:
                        return cache[k]
                except KeyError:
                    pass  # key not found
                v = await func(*args, **kwargs)
                try:
                    async with lock:
                        cache.setdefault(k, v)
                except ValueError:
                    pass  # value too large
                return v

            async def clear():
                async with lock:
                    cache.clear()

        else:

            def wrapper(*args, **kwargs):
                k = key(*args, **kwargs)
                try:
                    with lock:
                        return cache[k]
                except KeyError:
                    pass  # key not found
                v = func(*args, **kwargs)
                try:
                    with lock:
                        cache.setdefault(k, v)
                except ValueError:
                    pass  # value too large
                return v

            def clear():
                with lock:
                    cache.clear()

        wrapper.cache = cache
        wrapper.cache_key = key
        wrapper.cache_lock = lock
        wrapper.cache_clear = clear

        return functools.update_wrapper(wrapper, func)

    return decorator
