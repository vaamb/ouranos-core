import asyncio
import functools
from contextlib import AbstractContextManager
from typing import Any, Callable, MutableMapping, Optional, Type, TypeVar

from cachetools import keys
from sqlalchemy.ext.asyncio import AsyncSession

from ouranos.core.database.models.abc import Base


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


def clearer(
    cache: Optional[MutableMapping[_KT, Any]],
    key: Callable[..., _KT] = keys.hashkey,
    lock: Optional[AbstractContextManager[Any]] = None,
) :
    """Decorator to wrap a function to clear some cache results.
    """
    lock = lock or NullContext()

    def decorator(func):
        if asyncio.iscoroutinefunction(func):

            async def wrapper(*args, **kwargs):
                k = key(*args, **kwargs)
                v = await func(*args, **kwargs)
                async with lock:
                    cache.pop(k, None)
                return v

        else:

            def wrapper(*args, **kwargs):
                k = key(*args, **kwargs)
                v = func(*args, **kwargs)
                with lock:
                    cache.pop(k, None)
                return v

        wrapper.cache = cache
        wrapper.cache_key = key
        wrapper.cache_lock = lock

        return functools.update_wrapper(wrapper, func)

    return decorator


def create_hashable_key(**kwargs: dict[str: Any]) -> tuple:
    to_freeze = []
    def append_if_hashable(key: str, value: Any) -> None:
        nonlocal to_freeze
        try:
            hash(value)
        except TypeError:
            raise TypeError(f"Cannot hash {key}'s value {value}")
        else:
            to_freeze.append((key, value))

    for key, value in sorted(kwargs.items()):
        if isinstance(value, list):
            frozen_value = tuple(value)
            append_if_hashable(key, frozen_value)
        #elif isinstance(value, dict):
        #    to_freeze.append((key, create_hashable_key(**value)))
        else:
            append_if_hashable(key, value)
    return tuple(to_freeze)


def sessionless_hashkey(
        cls_or_self: Type[Base] | Base,
        session: AsyncSession,
        /,
        **kwargs
) -> tuple:
    #if isinstance(cls_or_self, Base):
    #    if hasattr(cls_or_self, "id"):
    #        kwargs["id"] = cls_or_self.id
    #    if hasattr(cls_or_self, "uid"):
    #        kwargs["uid"] = cls_or_self.uid
    return create_hashable_key(**kwargs)
