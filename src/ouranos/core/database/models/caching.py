from __future__ import annotations

import asyncio
import functools
from contextlib import AbstractContextManager
from typing import Any, Callable, MutableMapping, Optional, Self, Type, TypeVar

from cachetools import keys
from sqlalchemy.ext.asyncio import AsyncSession

from ouranos.core.database.models.abc import (
    Base, CRUDMixin, lookup_keys_type, on_conflict_opt)


_KT = TypeVar("_KT")


class NullContext:
    """A no-op context manager compatible with both sync and async usage.

    Used as a default lock when no lock is provided to caching decorators,
    allowing uniform `with lock:` / `async with lock:` syntax without
    branching.
    """

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

    A mix from cachetools and asyncache. Supports both sync and async functions.
    Uses `setdefault` on cache write to handle concurrent misses gracefully —
    if two coroutines miss the cache simultaneously, only the first result is
    stored and both return the same cached value.

    :param cache: A MutableMapping used to store results.
    :param key: A callable that derives the cache key from the function arguments.
    :param lock: An optional context manager used to synchronize cache access.
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
    """Decorator to wrap a classmethod with a memoizing callable that stores
    results in `cls._cache`.

    Similar to `cached` but designed for classmethods where the cache is
    stored on the class itself rather than passed as an argument. The class
    must define a `_cache` attribute (a MutableMapping).

    Note: only the async branch is currently used and tested.

    :param key: A callable that derives the cache key from the method arguments.
    :param lock: An optional context manager used to synchronize cache access.
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
                v = method(cls, *args, **kwargs)
                try:
                    with lock:
                        cls._cache.setdefault(k, v)
                except ValueError:
                    pass  # value too large
                return v

        return functools.update_wrapper(wrapper, method)

    return decorator


def clearing_cache(
    cache: Optional[MutableMapping[_KT, Any]],
    key: Callable[..., _KT] = keys.hashkey,
    lock: Optional[AbstractContextManager[Any]] = None,
):
    """Decorator to invalidate a specific cache entry after a function runs.

    Calls the wrapped function first, then removes the matching cache entry.
    If the function raises, the cache is not cleared — this is intentional for
    write operations where a failed write should not invalidate the cache.

    :param cache: The MutableMapping to clear entries from.
    :param key: A callable that derives the cache key from the function arguments.
    :param lock: An optional context manager used to synchronize cache access.
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


def clearing_cache_method(
    key: Callable[..., _KT] = keys.hashkey,
    lock: Optional[AbstractContextManager[Any]] = None,
):
    """Decorator to invalidate a specific entry in `cls._cache` after a
    method runs.

    The classmethod equivalent of `clearer`. Calls the method first, then
    removes the matching entry from `cls._cache`. If the method raises, the
    cache is not cleared.

    :param key: A callable that derives the cache key from the method arguments.
    :param lock: An optional context manager used to synchronize cache access.
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


def create_hashable_key(**kwargs: dict[str, Any]) -> tuple:
    """Convert keyword arguments into a sorted, hashable tuple for use as a
    cache key.

    Recursively converts lists to tuples and nested dicts to nested tuples,
    ensuring the result is always hashable. Keys are sorted to guarantee a
    stable ordering regardless of the argument order at the call site.
    """
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
    """Build a cache key from keyword arguments, ignoring the session.

    When `cls_or_self` is an instance rather than a class, its `id` or
    `uid` attribute is included in the key to distinguish results across
    different instances of the same class.
    """
    if isinstance(cls_or_self, Base):
        if hasattr(cls_or_self, "id"):
            kwargs["id"] = cls_or_self.id
        if hasattr(cls_or_self, "uid"):
            kwargs["uid"] = cls_or_self.uid
    return create_hashable_key(**kwargs)


def hash_get(
        cls: Type[Base],
        session: AsyncSession,
        /,
        **lookup_keys,
) -> tuple:
    """Cache key function for `@cached_method` on lookup operations.

    Derives the key from `lookup_keys` only, ignoring the session.
    """
    return create_hashable_key(**lookup_keys)


def hash_write(
        cls: Type[Base],
        session: AsyncSession,
        /,
        values: dict | None = None,
        _on_conflict_do: on_conflict_opt = None,
        **lookup_keys,
) -> tuple:
    """Cache key function for `@clearing_cache_method` on write operations.

    Matches the signature of `create` and `update` (which accept `values`
    and `_on_conflict_do`) while deriving the key from `lookup_keys` only.
    """
    return create_hashable_key(**lookup_keys)


def hash_delete(
        cls: Type[Base],
        session: AsyncSession,
        /,
        **lookup_keys,
) -> tuple:
    """Cache key function for `@clearing_cache_method` on delete operations.

    Matches the signature of `delete` (no `values` or `_on_conflict_do`)
    while deriving the key from `lookup_keys` only.
    """
    return create_hashable_key(**lookup_keys)


class CachedCRUDMixin(CRUDMixin):
    """A `CRUDMixin` extension that adds transparent caching to read
    operations and automatic cache invalidation to write operations.

    Subclasses must define a `_cache` class attribute (a MutableMapping).
    `get` results are stored in `_cache` and keyed by lookup keys.
    `create`, `update`, and `delete` automatically invalidate the
    relevant cache entry after each successful operation.
    """

    _cache: MutableMapping

    @classmethod
    def clear_cache(cls, /, **lookup_keys: lookup_keys_type) -> None:
        """Manually invalidate a specific cache entry by its lookup keys.

        All lookup keys must be provided. Raises `ValueError` if any
        required key is missing.
        """
        cls._check_lookup_keys(*lookup_keys.keys())
        key = create_hashable_key(**lookup_keys)
        cls._cache.pop(key, None)

    @classmethod
    @clearing_cache_method(key=hash_write)
    async def create(
            cls,
            session: AsyncSession,
            /,
            values: dict | None = None,
            _on_conflict_do: on_conflict_opt = None,
            **lookup_keys: lookup_keys_type,
    ) -> Self | None:
        """Create a new record and invalidate the corresponding cache entry."""
        return await super().create(
            session, values=values, _on_conflict_do=_on_conflict_do, **lookup_keys)

    @classmethod
    @cached_method(key=hash_get)
    async def get(
            cls,
            session: AsyncSession,
            /,
            **lookup_keys: lookup_keys_type,
    ) -> Self | None:
        """Fetch a record by its lookup keys, using the cache when available."""
        return await super().get(session, **lookup_keys)

    @classmethod
    @clearing_cache_method(key=hash_write)
    async def update(
            cls,
            session: AsyncSession,
            /,
            values: dict,
            **lookup_keys: lookup_keys_type,
    ) -> None:
        """Update a record and invalidate the corresponding cache entry."""
        return await super().update(session, values=values, **lookup_keys)

    @classmethod
    @clearing_cache_method(key=hash_delete)
    async def delete(
            cls,
            session: AsyncSession,
            /,
            **lookup_keys: lookup_keys_type,
    ) -> None:
        """Delete a record and invalidate the corresponding cache entry."""
        return await super().delete(session, **lookup_keys)
