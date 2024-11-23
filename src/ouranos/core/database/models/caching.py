from __future__ import annotations

import asyncio
from enum import Enum
import functools
from contextlib import AbstractContextManager
from typing import Any, Callable, MutableMapping, Optional, Self, Type, TypeVar
from uuid import UUID

from cachetools import keys
from sqlalchemy.ext.asyncio import AsyncSession

from ouranos.core.database.models.abc import Base, CRUDMixin


lookup_keys_type: str | Enum | UUID | bool
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
):
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


def cached_method(
    key: Callable[..., _KT] = keys.hashkey,
    lock: Optional[AbstractContextManager[Any]] = None,
):
    """Decorator to wrap a class method with a memoizing callable that saves
    results in a cache.

    A mix from cachetools and asyncache
    """
    lock = lock or NullContext()

    def decorator(method):
        if asyncio.iscoroutinefunction(method):

            async def wrapper(cls, *args, **kwargs):
                k = key(cls, *args, **kwargs)
                try:
                    async with lock:
                        return cls._cache[k]
                except KeyError:
                    pass  # key not found
                v = await method(cls, *args, **kwargs)
                try:
                    async with lock:
                        cls._cache.setdefault(k, v)
                except ValueError:
                    pass  # value too large
                return v

        else:

            def wrapper(cls, *args, **kwargs):
                k = key(cls, *args, **kwargs)
                try:
                    with lock:
                        return cls._cache[k]
                except KeyError:
                    pass  # key not found
                v = cls._cache(cls, *args, **kwargs)
                try:
                    with lock:
                        cls._cache.setdefault(k, v)
                except ValueError:
                    pass  # value too large
                return v

        return functools.update_wrapper(wrapper, method)

    return decorator


def clearer(
    cache: Optional[MutableMapping[_KT, Any]],
    key: Callable[..., _KT] = keys.hashkey,
    lock: Optional[AbstractContextManager[Any]] = None,
):
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


def clearing_method(
    key: Callable[..., _KT] = keys.hashkey,
    lock: Optional[AbstractContextManager[Any]] = None,
):
    """Decorator to wrap a method to clear some cache results.
    """
    lock = lock or NullContext()

    def decorator(method):
        if asyncio.iscoroutinefunction(method):

            async def wrapper(cls, *args, **kwargs):
                k = key(cls, *args, **kwargs)
                v = await method(cls, *args, **kwargs)
                async with lock:
                    cls._cache.pop(k, None)
                return v

        else:

            def wrapper(cls, *args, **kwargs):
                k = key(cls, *args, **kwargs)
                v = method(cls, *args, **kwargs)
                with lock:
                    cls._cache.pop(k, None)
                return v

        return functools.update_wrapper(wrapper, method)

    return decorator


def create_hashable_key(**kwargs: dict[str: Any]) -> tuple:
    to_freeze = []
    for key, value in sorted(kwargs.items()):
        if isinstance(value, list):
            value = tuple(value)
        elif isinstance(value, dict):
            value = create_hashable_key(**value)
        to_freeze.append((key, value))
    return tuple(to_freeze)


def sessionless_hashkey(
        cls_or_self: Type[Base] | Base,
        session: AsyncSession,
        /,
        **kwargs
) -> tuple:
    if isinstance(cls_or_self, Base):
        if hasattr(cls_or_self, "id"):
            kwargs["id"] = cls_or_self.id
        if hasattr(cls_or_self, "uid"):
            kwargs["uid"] = cls_or_self.uid
    return create_hashable_key(**kwargs)


def cached_hash(
        cls: Type[Base],
        session: AsyncSession,
        /,
        **lookup_keys,
) -> tuple:
    return create_hashable_key(**lookup_keys)


def clearer_hash(
        cls: Type[Base],
        session: AsyncSession,
        /,
        values: dict,
        **lookup_keys,
) -> tuple:
    return create_hashable_key(**lookup_keys)


class CachedCRUDMixin(CRUDMixin):
    _cache: MutableMapping

    @classmethod
    def clear_cache(cls, /, **lookup_keys: lookup_keys_type) -> None:
        cls._check_lookup_keys(*lookup_keys.keys())
        key = create_hashable_key(**lookup_keys)
        cls._cache.pop(key, None)

    @classmethod
    @clearing_method(key=clearer_hash)
    async def create(
            cls,
            session: AsyncSession,
            /,
            values: dict,
            **lookup_keys: lookup_keys_type,
    ) -> Self | None:
        return await super().create(session, values=values, **lookup_keys)

    @classmethod
    @cached_method(key=cached_hash)
    async def get(
            cls,
            session: AsyncSession,
            /,
            **lookup_keys: lookup_keys_type,
    ) -> Self | None:
        return await super().get(session, **lookup_keys)

    @classmethod
    @clearing_method(key=clearer_hash)
    async def update(
            cls,
            session: AsyncSession,
            /,
            values: dict,
            **lookup_keys: lookup_keys_type,
    ) -> None:
        return await super().update(session, values=values, **lookup_keys)

    @classmethod
    @clearing_method(key=clearer_hash)
    async def delete(
            cls,
            session: AsyncSession,
            /,
            **lookup_keys: lookup_keys_type,
    ) -> None:
        return await super().delete(session, **lookup_keys)
