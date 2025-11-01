from __future__ import annotations

from abc import abstractmethod
from datetime import datetime, timedelta, timezone
from enum import Enum
import typing as t
from typing import Callable, Literal, NamedTuple, Self, Sequence, Type, TypeAlias
from uuid import UUID
from warnings import warn

from sqlalchemy import (
    and_, Column, delete, Insert, inspect, Select, select, table, UnaryExpression,
    UniqueConstraint, update)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from gaia_validators import missing

from ouranos import db
from ouranos.core.database.models.types import UtcDateTime
from ouranos.core.utils import timeWindow


lookup_keys_type: TypeAlias = str | Enum | UUID | bool
on_conflict_opt: TypeAlias = Literal["update", "nothing"] | None


class ToDictMixin:
    def to_dict(self, exclude: list | None = None) -> dict:
        exclude: list = exclude or []
        return {
            key: value for key, value in vars(self).items()
            if (
                    key not in exclude
                    and not key.startswith("_")
            )
        }


class Base(db.Model, ToDictMixin):
    __abstract__ = True

    _dialect: str | None = None
    _insert: Callable[[table], Insert] | None = None

    @classmethod
    def _get_dialect(cls) -> str:
        if cls._dialect is None:
            table = db.Model.metadata.tables[cls.__tablename__]
            bind_key = table.info.get("bind_key", None)
            engine = db.get_engine_for_bind(bind_key)
            cls._dialect = engine.dialect.name
        return cls._dialect

    @classmethod
    def _get_insert(cls) -> Callable[[table], Insert]:
        """Get a dialect-specific `insert`"""
        if cls._insert is None:
            dialect = cls._get_dialect()
            if dialect in ["mariadb", "mysql"]:
                from sqlalchemy.dialects.mysql import insert
                cls._insert = insert
            elif dialect == "postgresql":
                from sqlalchemy.dialects.postgresql import insert
                cls._insert = insert
            elif dialect == "sqlite":
                from sqlalchemy.dialects.sqlite import insert
                cls._insert = insert
            else:
                from sqlalchemy import insert
                cls._insert = insert
        return cls._insert


class CRUDMixin:
    _lookup_keys: list[str] | None = None
    __lookup_keys: list[str] | None = None

    _on_conflict_do: Callable[[Insert, str], Insert] | None = None

    @classmethod
    def _get_lookup_keys(cls: Base) -> list[str]:
        if cls.__lookup_keys is None:
            # Get the columns with a unique constraint
            # Try to get a unique constraint from the table args
            unique: list[str] = []
            if hasattr(cls, "__table_args__"):
                for arg in cls.__table_args__:
                    if isinstance(arg, UniqueConstraint):
                        unique = [column.name for column in arg.columns]
                        break
            # Try to get a unique constraint from the columns "unique" and "primary_key" args
            else:
                columns: list[Column] = inspect(cls).columns
                unique = [column.name for column in columns if column.unique]
                if not unique:
                    unique = [column.name for column in columns if column.primary_key]
            if not unique:
                raise ValueError(
                    f"Table {cls.__tablename__} has no unique constraint"
                )

            # If the lookup keys are not set, use the unique constraint
            if not cls._lookup_keys:
                cls.__lookup_keys = unique
            # If the lookup keys are set, make sure they are valid
            else:
                # Make sure the lookup keys are valid columns
                for lookup_key in cls._lookup_keys:
                    if not hasattr(cls, lookup_key):
                        raise ValueError(
                            f"Lookup key {lookup_key} is not a column of {cls.__tablename__}"
                        )
                if not all(lookup_key in unique for lookup_key in cls._lookup_keys):
                    raise ValueError(
                        f"Table {cls.__tablename__} has no unique constraint on "
                        f"the lookup keys {cls._lookup_keys}"
                    )
                cls.__lookup_keys = cls._lookup_keys
        return cls.__lookup_keys

    @classmethod
    def _check_lookup_keys(cls: Base, *lookup_keys: str) -> None:
        valid_lookup_keys = cls._get_lookup_keys()
        if not all(lookup_key in lookup_keys for lookup_key in valid_lookup_keys):
            raise ValueError("You should provide all the lookup keys")

    @classmethod
    def _get_on_conflict_do(
            cls: Type[Base] | Type[CRUDMixin],
    ) -> Callable[[Insert, str], Insert]:
        if cls._on_conflict_do is None:
            dialect = cls._get_dialect()

            if dialect in ["mariadb", "mysql"]:
                if t.TYPE_CHECKING:
                    from sqlalchemy.dialects.mysql import Insert

                def impl(stmt: Insert, action: str) -> Insert:
                    if action == "nothing":
                        stmt = stmt.on_duplicate_key_update(
                            {cls._lookup_keys[0]: getattr(stmt.inserted, cls._lookup_keys[0])},
                        )
                    elif action == "update":
                        stmt = stmt.on_duplicate_key_update(
                            {"data": stmt.inserted.data},
                        )
                    else:
                        raise ValueError
                    return stmt

            elif dialect == "postgresql":
                if t.TYPE_CHECKING:
                    from sqlalchemy.dialects.postgresql import Insert

                def impl(stmt: Insert, action: str) -> Insert:
                    if action == "nothing":
                        stmt = stmt.on_conflict_do_nothing(
                            index_elements=cls._get_lookup_keys(),
                        )
                    elif action == "update":
                        columns_name = inspect(cls).attrs.keys()
                        stmt = stmt.on_conflict_do_update(
                            index_elements=cls._get_lookup_keys(),
                            set_={
                                column: getattr(stmt.excluded, column)
                                for column in columns_name
                                if column not in cls._get_lookup_keys()
                            },
                        )
                    else:
                        raise ValueError
                    return stmt

            elif dialect == "sqlite":
                if t.TYPE_CHECKING:
                    from sqlalchemy.dialects.sqlite import Insert

                def impl(stmt: Insert, action: str) -> Insert:
                    if action == "nothing":
                        stmt = stmt.on_conflict_do_nothing(
                            index_elements=cls._get_lookup_keys(),
                        )
                    elif action == "update":
                        columns_name = inspect(cls).attrs.keys()
                        stmt = stmt.on_conflict_do_update(
                            index_elements=cls._get_lookup_keys(),
                            set_={
                                column: getattr(stmt.excluded, column)
                                for column in columns_name
                                if column not in cls._get_lookup_keys()
                            },
                        )
                    else:
                        raise ValueError
                    return stmt

            else:
                warn(
                    f"Dialect '{dialect}' is not yet supported. Feel free to "
                    f"add it.")

                def impl(stmt: Insert, action: str) -> Insert:
                    if action not in ["nothing", "update"]:
                        raise ValueError
                    return stmt

            cls._on_conflict_do = impl
        return cls._on_conflict_do

    @classmethod
    async def create(
            cls: Base,
            session: AsyncSession,
            /,
            values: dict | None = None,
            _on_conflict_do: on_conflict_opt = None,
            **lookup_keys: lookup_keys_type,
    ) -> None:
        cls._check_lookup_keys(*lookup_keys.keys())
        values = values or {}
        insert = cls._get_insert()
        stmt = insert(cls).values(**lookup_keys, **values)
        if _on_conflict_do:
            if cls._on_conflict_do is None:
                cls._on_conflict_do = cls._get_on_conflict_do()
            stmt = cls._on_conflict_do(stmt, _on_conflict_do)
        await session.execute(stmt)

    @classmethod
    async def create_multiple(
            cls: Base,
            session: AsyncSession,
            /,
            values: list[dict] | list[NamedTuple],
            _on_conflict_do: on_conflict_opt = None,
    ) -> None:
        insert = cls._get_insert()
        stmt = insert(cls).values(values)
        if _on_conflict_do:
            if cls._on_conflict_do is None:
                cls._on_conflict_do = cls._get_on_conflict_do()
            stmt = cls._on_conflict_do(stmt, _on_conflict_do)
        await session.execute(stmt)

    @classmethod
    def _generate_get_query(
            cls: Base,
            offset: int | None = None,
            limit: int | None = None,
            order_by: str | None = None,
            **lookup_keys: list[lookup_keys_type] | lookup_keys_type | None,
    ) -> Select:
        stmt = select(cls)
        for key, value in lookup_keys.items():
            if value is None:
                continue
            if isinstance(value, list):
                stmt = stmt.where(cls.__table__.c[key].in_(value))
            else:
                stmt = stmt.where(cls.__table__.c[key] == value)
        if offset is not None:
            stmt = stmt.offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)
        if order_by is not None:
            stmt = stmt.order_by(order_by)
        return stmt

    @classmethod
    async def get(
            cls: Base,
            session: AsyncSession,
            /,
            offset: int | None = None,
            limit: int | None = None,
            order_by: UnaryExpression | None = None,
            **lookup_keys: list[lookup_keys_type] | lookup_keys_type | None,
    ) -> Self | None:
        """
        :param offset: the offset from which to start looking
        :param limit: the maximum number of rows to query
        :param order_by: how to order the results
        :param session: an AsyncSession instance
        :param lookup_keys: a dict with table column names as keys and values
                            depending on the related column data type
        """
        stmt = cls._generate_get_query(offset, limit, order_by, **lookup_keys)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @classmethod
    async def get_multiple(
            cls: Base,
            session: AsyncSession,
            /,
            offset: int | None = None,
            limit: int | None = None,
            order_by: UnaryExpression | None = None,
            **lookup_keys: list[lookup_keys_type] | lookup_keys_type | None,
    ) -> Sequence[Self]:
        """
        :param session: an AsyncSession instance
        :param offset: the offset from which to start looking
        :param limit: the maximum number of rows to query
        :param order_by: how to order the results
        :param lookup_keys: a dict with table column names as keys and values
                            depending on the related column data type
        """
        stmt = cls._generate_get_query(offset, limit, order_by, **lookup_keys)
        result = await session.execute(stmt)
        return result.scalars().all()

    @classmethod
    async def update(
            cls: Base,
            session: AsyncSession,
            /,
            values: dict,
            **lookup_keys: lookup_keys_type,
    ) -> None:
        cls._check_lookup_keys(*lookup_keys.keys())
        stmt = (
            update(cls)
            .where(
                and_(
                    cls.__table__.c[key] == value
                    for key, value in lookup_keys.items()
                )
            )
            .values({
                key: value
                for key, value in values.items()
                if value is not missing
            })
        )
        await session.execute(stmt)

    @classmethod
    async def update_multiple(
            cls: Base,
            session: AsyncSession,
            /,
            values: list[dict],
    ) -> None:
        await session.execute(
            update(cls),
            values
        )

    @classmethod
    async def delete(
            cls: Base,
            session: AsyncSession,
            /,
            **lookup_keys: lookup_keys_type,
    ) -> None:
        cls._check_lookup_keys(*lookup_keys.keys())
        stmt = (
            delete(cls)
            .where(
                and_(
                    cls.__table__.c[key] == value
                    for key, value in lookup_keys.items()
                )
            )
        )
        await session.execute(stmt)

    @classmethod
    async def update_or_create(
            cls: Self,
            session: AsyncSession,
            /,
            values: dict | None = None,
            **lookup_keys: lookup_keys_type,
    ) -> None:
        #cls._check_lookup_keys(*lookup_keys.keys())
        obj = await cls.get(session, **lookup_keys)
        if not obj:
            await cls.create(session, values=values, **lookup_keys)
        elif values:
            await cls.update(session, values=values, **lookup_keys)

    @classmethod
    async def get_or_create(
            cls: Self,
            session: AsyncSession,
            /,
            values: dict | None = None,
            **lookup_keys: lookup_keys_type,
    ) -> Self:
        obj = await cls.get(session, **lookup_keys)
        if obj is None:
            await cls.create(session, values=values, **lookup_keys)
        return await cls.get(session, **lookup_keys)


class RecordMixin(CRUDMixin):
    """Records are Models with at least one `timestamp` column that can be
    queried with a `timeWindow`"""

    timestamp: Mapped[datetime] = mapped_column(UtcDateTime)

    @classmethod
    async def get_records(
            cls: Base,
            session: AsyncSession,
            /,
            offset: int | None = None,
            limit: int | None = None,
            order_by: UnaryExpression | None = None,
            time_window: timeWindow | None = None,
            **lookup_keys: list[lookup_keys_type] | lookup_keys_type | None,
    ) -> Sequence[Base]:
        stmt = cls._generate_get_query(offset, limit, order_by, **lookup_keys)
        if time_window:
            stmt = stmt.where(
                (cls.timestamp > time_window.start)
                & (cls.timestamp <= time_window.end)
            )
        stmt = stmt.order_by(cls.timestamp.asc())
        result = await session.execute(stmt)
        return result.scalars().all()


class CacheMixin(CRUDMixin):
    timestamp: Mapped[datetime] = mapped_column(UtcDateTime)

    @classmethod
    @abstractmethod
    def get_ttl(cls: Base) -> int:
        """Return data TTL in seconds"""
        raise NotImplementedError

    @classmethod
    async def insert_data(
            cls: Base,
            session: AsyncSession,
            values: dict | list[dict]
    ) -> None:
        await cls.remove_expired(session)
        await cls.create_multiple(session, values=values, _on_conflict_do="update")

    @classmethod
    async def get_recent(
            cls: Base,
            session: AsyncSession,
            **lookup_keys: list[lookup_keys_type] | lookup_keys_type | None,
    ) -> Sequence[Base]:
        stmt = cls._generate_get_query(**lookup_keys)
        time_limit = datetime.now(timezone.utc) - timedelta(seconds=cls.get_ttl())
        stmt = stmt.where(cls.timestamp > time_limit)
        result = await session.execute(stmt)
        return result.scalars().all()

    @classmethod
    async def remove_expired(cls, session: AsyncSession) -> None:
        time_limit = datetime.now(timezone.utc) - timedelta(seconds=cls.get_ttl())
        stmt = delete(cls).where(cls.timestamp < time_limit)
        await session.execute(stmt)

    @classmethod
    async def clear(cls: Base, session: AsyncSession) -> None:
        stmt = delete(cls)
        await session.execute(stmt)
