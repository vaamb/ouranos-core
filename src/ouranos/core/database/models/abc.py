from __future__ import annotations

from datetime import datetime, timedelta, timezone
from enum import Enum
import typing as t
from typing import (
    Any, Callable, Collection, Literal, Self, Sequence, TypeAlias)
from uuid import UUID
from warnings import warn

from sqlalchemy import (
    and_, Column, ColumnCollection,  delete, Insert, Select, select, Table,
    tuple_, UnaryExpression, UniqueConstraint, update)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.schema import ColumnDefault
from sqlalchemy.orm import class_mapper, Mapped, mapped_column

from gaia_validators import missing

from ouranos import db
from ouranos.core.database.models.types import UtcDateTime
from ouranos.core.database.models.utils import StmtModifier


lookup_keys_type: TypeAlias = str | int | Enum | UUID | bool
query_keys_type: TypeAlias = lookup_keys_type | StmtModifier | None
on_conflict_opt: TypeAlias = Literal["update", "nothing"] | None


class ToDictMixin:
    def to_dict(self, exclude: list | None = None) -> dict:
        """Return the instance's loaded attributes as a dict.

        :param exclude: the names of the attributes to leave out. Private
                        attributes (starting with "_") are always left out.
        """
        # /!\\ does not work with lazy loaded attributes as they won't be in `vars(self)`.
        # However, async SQLAlchemy does not use lazy loading
        exclude: list = exclude or []
        return {
            key: value for key, value in vars(self).items()
            if (
                    key not in exclude
                    and not key.startswith("_")
            )
        }


class Base(db.Model, ToDictMixin):  # ty: ignore[invalid-base]
    __abstract__ = True

    _dialect: str | None = None
    _insert: Callable[[Any], Insert] | None = None

    @classmethod
    def _get_dialect(cls) -> str:
        if cls._dialect is None:
            bind_key = cls.__table__.info.get("bind_key", None)
            engine = db.get_engine_for_bind(bind_key)
            cls._dialect = engine.dialect.name
        assert cls._dialect is not None
        return cls._dialect

    @classmethod
    def _get_insert(cls) -> Callable[[Any], Insert]:
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
        assert cls._insert is not None
        return cls._insert


class CRUDMixin:
    """
    A Mixin that implements CRUD methods for SQLAlchemy async ORM classes.

    The main aim of this class is to remove the boilerplate:
        result = await session.execute(select(...))
        return result.scalars().all()

    It does not provide single-row `update()` and `delete()` as, without
    lookup keys, nothing guarantees they target a single row. Use
    `UniqueCRUDMixin` for that.
    """
    if t.TYPE_CHECKING:
        __tablename__: str
        __table__: Table
        __table_args__: tuple | dict

        _get_dialect: Callable[[], str]
        _get_insert: Callable[[], Callable[[Any], Insert]]

    @classmethod
    async def create(
            cls,
            session: AsyncSession,
            /,
            values: dict,
    ) -> None:
        """Insert a single row.

        :param session: an AsyncSession instance
        :param values: a dict with table column names as keys and the row
                       values as values
        """
        insert = cls._get_insert()
        stmt = insert(cls).values(**values)
        await session.execute(stmt)

    @classmethod
    async def create_multiple(
            cls,
            session: AsyncSession,
            /,
            values: list[dict],
    ) -> None:
        """Insert multiple rows in a single statement.

        :param session: an AsyncSession instance
        :param values: a list of dicts, each one containing the values of a
                       row to insert
        """
        insert = cls._get_insert()
        stmt = insert(cls).values(values)
        await session.execute(stmt)

    @classmethod
    def _generate_get_query(
            cls,
            offset: int | None = None,
            limit: int | None = None,
            order_by: str | UnaryExpression | None = None,
            **lookup_keys: list[query_keys_type] | query_keys_type | None,
    ) -> Select:
        stmt = select(cls)
        for key, value in lookup_keys.items():
            if value is None:
                continue
            elif isinstance(value, StmtModifier):
                stmt = value.modify_stmt(stmt, getattr(cls, key))
            elif isinstance(value, list):
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
            cls,
            session: AsyncSession,
            /,
            offset: int | None = None,
            limit: int | None = None,
            order_by: str | UnaryExpression | None = None,
            **lookup_keys: list[query_keys_type] | query_keys_type | None,
    ) -> Self | None:
        """Get a single row, identified by its primary key.

        :param session: an AsyncSession instance
        :param offset: the offset from which to start looking
        :param limit: the maximum number of rows to query
        :param order_by: how to order the results
        :param lookup_keys: a dict with table column names as keys and values
                            depending on the related column data type
        """
        stmt = cls._generate_get_query(offset, limit, order_by, **lookup_keys)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @classmethod
    async def get_multiple(
            cls,
            session: AsyncSession,
            /,
            offset: int | None = None,
            limit: int | None = None,
            order_by: str | UnaryExpression | None = None,
            **lookup_keys: list[query_keys_type] | query_keys_type | None,
    ) -> Sequence[Self]:
        """Get multiple rows, identified by their primary key.

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
    async def update_multiple(
            cls,
            session: AsyncSession,
            /,
            values: list[dict],
    ) -> None:
        """Update multiple rows, identified by their primary key.

        :param session: an AsyncSession instance
        :param values: a list of dicts, each containing the primary key
                       column(s) of a row to update along with the new values
        """
        await session.execute(
            update(cls),
            values
        )

    @classmethod
    async def delete_multiple(
            cls,
            session: AsyncSession,
            /,
            values: list[dict],
    ) -> None:
        """Delete the rows whose primary key is in `values`.

        :param values: a list of dicts, each containing the primary key
                       column(s) of a row to delete. Other keys are ignored.
        """
        if not values:
            return
        primary_key = class_mapper(cls).primary_key
        if len(primary_key) == 1:
            column = primary_key[0]
            stmt = (
                delete(cls)
                .where(column.in_([value[column.name] for value in values]))
            )
        else:
            stmt = (
                delete(cls)
                .where(
                    tuple_(*primary_key).in_([
                        tuple(value[column.name] for column in primary_key)
                        for value in values
                    ])
                )
            )
        await session.execute(stmt)


class UniqueCRUDMixin(CRUDMixin):
    """
    A `CRUDMixin` extension for tables whose rows are identified by lookup
    keys, which must be covered by a unique constraint.

    The lookup keys are either explicitly given by `_lookup_keys` or inferred
    from the table's unique constraint, unique columns or primary key. They
    are required by `create()`, `update()` and `delete()`, so the latter two
    always target a single row.
    """
    _lookup_keys: list[str] | None = None
    _validated_lookup_keys: list[str] | None = None

    @classmethod
    def _get_unique_columns(cls) -> list[str]:
        # Get the columns with a unique constraint
        # Try to get a unique constraint from the table args
        table_args = getattr(cls, "__table_args__", None)
        if table_args is not None:
            rv: list[str] | None = None
            if isinstance(table_args, tuple):
                for arg in table_args:
                    if isinstance(arg, UniqueConstraint):
                        if rv is not None:
                            # There should only be one `UniqueConstraint`
                            raise ValueError(
                                "`_get_unique_columns()` currently only works with "
                                "a single `UniqueConstraint`"
                            )
                        rv = [column.name for column in arg.columns]
            if rv is not None:
                return rv

        # If we did not find a unique constraint, try to get it from the columns
        # "unique" args
        columns: ColumnCollection = class_mapper(cls).columns
        unique = [column.name for column in columns if column.unique]
        if not unique:
            unique = [column.name for column in columns if column.primary_key]
        if unique:
            return unique
        raise ValueError(
            f"Table {getattr(cls, '__tablename__', repr(cls))} has no unique constraint"
        )

    @classmethod
    def _validate_lookup_keys(
            cls,
            lookup_keys: list[str],
            unique_columns: list[str],
    ) -> None:
        # Make sure the lookup keys are valid columns
        tablename = getattr(cls, "__tablename__", repr(cls))
        for lookup_key in lookup_keys:
            if not hasattr(cls, lookup_key):
                raise ValueError(
                    f"Lookup key {lookup_key} is not a column of {tablename}"
                )
        if not all(lookup_key in unique_columns for lookup_key in lookup_keys):
            raise ValueError(
                f"Table {tablename} has no unique constraint on "
                f"the lookup keys {lookup_keys}"
            )

    @classmethod
    def _get_lookup_keys(cls) -> list[str]:
        if cls._validated_lookup_keys is None:
            unique_columns = cls._get_unique_columns()
            # If no lookup keys are suggested, use the unique constraint
            if cls._lookup_keys is None:
                cls._validated_lookup_keys = unique_columns
            # If some lookup keys were suggested, make sure they are valid
            else:
                cls._validate_lookup_keys(cls._lookup_keys, unique_columns)
                cls._validated_lookup_keys = cls._lookup_keys
        assert cls._validated_lookup_keys is not None
        return cls._validated_lookup_keys

    @classmethod
    def _check_lookup_keys(cls, *lookup_keys: str) -> None:
        valid_lookup_keys = cls._get_lookup_keys()
        if not all(lookup_key in lookup_keys for lookup_key in valid_lookup_keys):
            raise ValueError("You should provide all the lookup keys")

    @classmethod
    async def create(
            cls,
            session: AsyncSession,
            /,
            values: dict | None = None,
            **lookup_keys: lookup_keys_type,
    ) -> None:
        """Insert a single row.

        :param session: an AsyncSession instance
        :param values: a dict with the non-lookup column names as keys and
                       the row values as values
        :param lookup_keys: all the lookup keys of the row, with table column
                            names as keys and row values as values
        """
        cls._check_lookup_keys(*lookup_keys.keys())
        await super().create(session, values={**lookup_keys, **(values or {})})

    @classmethod
    async def update(
            cls,
            session: AsyncSession,
            /,
            values: dict,
            **lookup_keys: lookup_keys_type,
    ) -> None:
        """Update the row identified by the lookup keys.

        :param session: an AsyncSession instance
        :param values: a dict with table column names as keys and the new
                       values as values. Entries whose value is `missing` are
                       ignored.
        :param lookup_keys: all the lookup keys of the row, with table column
                            names as keys and row values as values
        """
        values = {
            key: value
            for key, value in values.items()
            # The values received can be generated by `pydantic` and `fastapi`
            # and sometimes, a `missing` sentinel is used rather than removing
            # the entry all together
            if value is not missing
        }
        if not values:
            return
        cls._check_lookup_keys(*lookup_keys.keys())
        stmt = (
            update(cls)
            .where(
                and_(
                    cls.__table__.c[key] == value  # ty: ignore[invalid-argument-type]
                    for key, value in lookup_keys.items()
                )
            )
            .values(values)
        )
        await session.execute(stmt)

    @classmethod
    async def delete(
            cls,
            session: AsyncSession,
            /,
            **lookup_keys: lookup_keys_type,
    ) -> None:
        """Delete the row identified by the lookup keys.

        :param session: an AsyncSession instance
        :param lookup_keys: all the lookup keys of the row, with table column
                            names as keys and row values as values
        """
        cls._check_lookup_keys(*lookup_keys.keys())
        stmt = (
            delete(cls)
            .where(
                and_(
                    cls.__table__.c[key] == value  # ty: ignore[invalid-argument-type]
                    for key, value in lookup_keys.items()
                )
            )
        )
        await session.execute(stmt)


class UpsertCRUDMixin(UniqueCRUDMixin):
    """
    A `UniqueCRUDMixin` extension that adds dialect-aware upserts, using the
    lookup keys as the conflict target.

    `create()` and `create_multiple()` accept an `_on_conflict_do` argument,
    and two upsert methods, `get_or_create()` and `update_or_create()`, which
    SQLAlchemy does not provide natively, are added.
    """
    _on_conflict_do: Callable[[Insert, str, Collection[str]], Insert] | None = None

    @classmethod
    def _get_onupdate_columns(cls) -> list[tuple[str, ColumnDefault]]:
        # Columns with an explicit `onupdate=`, whose value must be recomputed
        # on every conflict
        columns: ColumnCollection = class_mapper(cls).columns
        return [
            (column.name, column.onupdate)
            for column in columns
            if isinstance(column.onupdate, ColumnDefault)
        ]

    @classmethod
    def _get_on_conflict_update_values(
            cls,
            source: Any,
            columns: Collection[str],
            lookup_keys: Collection[str],
            onupdate_columns: Collection[tuple[str, ColumnDefault]],
    ) -> dict[str, Any]:
        """Build the "set" mapping used by an "on conflict do update" clause.

        :param source: the dialect-specific proxy to the rejected row
            (`stmt.excluded` on PostgreSQL/SQLite, `stmt.inserted` on MySQL).
        :param columns: the columns supplied to `create{_multiple}`.
        :param lookup_keys: the columns identifying the conflicting row,
            never updated.
        :param onupdate_columns: `(name, onupdate)` pairs of the columns with an
            explicit `onupdate=` default.
        """
        # Only update the columns supplied to the `create{_multiple}` method if
        # they are not "lookup" columns.
        to_update: dict[str, Any] = {
            column: getattr(source, column)
            for column in columns
            if column not in lookup_keys
        }
        # Columns with an explicit `onupdate=` are refreshed on conflict even
        # when they were not part of the supplied `values` (e.g.
        # `SensorDataCache.logged`, which needs to be reset to `False` whenever
        # new data for the same lookup keys comes in). As with SQLAlchemy's own
        # `onupdate`, a value explicitly supplied in `values` takes precedence.
        # Callable defaults are evaluated here, for each statement, rather
        # than once when the closure is built, so that time-based defaults
        # (`onupdate=datetime.now` for example) are not frozen.
        for column, onupdate in onupdate_columns:
            if column in to_update or column in lookup_keys:
                continue
            if onupdate.is_callable:
                to_update[column] = onupdate.arg(None)
            else:
                to_update[column] = onupdate.arg
        return to_update

    @classmethod
    def _get_on_conflict_do(cls) -> Callable[[Insert, str, Collection[str]], Insert]:
        if cls._on_conflict_do is None:
            dialect = cls._get_dialect()

            if dialect in {"mariadb", "mysql"}:
                if t.TYPE_CHECKING:
                    from sqlalchemy.dialects.mysql import Insert

                lookup_keys = cls._get_lookup_keys()
                onupdate_columns = cls._get_onupdate_columns()

                def impl(stmt: Insert, action: str, columns: Collection[str]) -> Insert:
                    if action not in ("nothing", "update"):
                        raise ValueError(
                            f"Unknown on conflict action '{action}', should be "
                            f"'nothing' or 'update'"
                        )
                    to_update: dict[str, Any] = {}
                    if action == "update":
                        to_update = cls._get_on_conflict_update_values(
                            stmt.inserted, columns, lookup_keys, onupdate_columns)  # ty: ignore[unresolved-attribute]
                    if not to_update:
                        # Either "nothing" was requested, or there is no column
                        # to update (SQLAlchemy refuses an empty update
                        # mapping). Assign the lookup column to itself rather
                        # than to the value from `stmt.inserted`:
                        # `ON DUPLICATE KEY UPDATE` fires on a conflict with
                        # *any* unique index, and if the conflicting index is
                        # not the lookup key, `stmt.inserted` would overwrite
                        # the existing row's lookup key with the new value
                        to_update = {lookup_keys[0]: stmt.table.c[lookup_keys[0]]}
                    return stmt.on_duplicate_key_update(to_update)  # ty: ignore[unresolved-attribute]

            elif dialect in {"postgresql", "sqlite"}:
                if t.TYPE_CHECKING:
                    if dialect == "postgresql":
                        from sqlalchemy.dialects.postgresql import Insert
                    else:
                        from sqlalchemy.dialects.sqlite import Insert

                lookup_keys = cls._get_lookup_keys()
                onupdate_columns = cls._get_onupdate_columns()

                def impl(stmt: Insert, action: str, columns: Collection[str]) -> Insert:
                    if action not in ("nothing", "update"):
                        raise ValueError(
                            f"Unknown on conflict action '{action}', should be "
                            f"'nothing' or 'update'"
                        )
                    to_update: dict[str, Any] = {}
                    if action == "update":
                        to_update = cls._get_on_conflict_update_values(
                            stmt.excluded, columns, lookup_keys, onupdate_columns)  # ty: ignore[unresolved-attribute]
                    if not to_update:
                        # Either "nothing" was requested, or there is no column
                        # to update (SQLAlchemy refuses an empty update mapping)
                        return stmt.on_conflict_do_nothing(  # ty: ignore[unresolved-attribute]
                            index_elements=lookup_keys,
                        )
                    return stmt.on_conflict_do_update(  # ty: ignore[unresolved-attribute]
                        index_elements=lookup_keys,
                        set_=to_update,
                    )

            else:
                warn(
                    f"Dialect '{dialect}' is not yet supported. Feel free to "
                    f"add it.", stacklevel=2)

                def impl(stmt: Insert, action: str, columns: Collection[str]) -> Insert:
                    if action not in ("nothing", "update"):
                        raise ValueError(
                            f"Unknown on conflict action '{action}', should be "
                            f"'nothing' or 'update'"
                        )
                    return stmt

            cls._on_conflict_do = impl  # ty: ignore[invalid-assignment]
        assert cls._on_conflict_do is not None
        return cls._on_conflict_do

    @classmethod
    # Valid ignore: `UniqueCRUDMixin.create()`'s `**lookup_keys` would also accept
    # an `_on_conflict_do` key, but lookup keys are columns and never private
    async def create(  # ty: ignore[invalid-method-override]
            cls,
            session: AsyncSession,
            /,
            values: dict | None = None,
            _on_conflict_do: on_conflict_opt = None,
            **lookup_keys: lookup_keys_type,
    ) -> None:
        """Insert a single row, optionally handling a lookup keys conflict.

        :param session: an AsyncSession instance
        :param values: a dict with the non-lookup column names as keys and
                       the row values as values
        :param _on_conflict_do: what to do if a row with the same lookup keys
                                already exists: "update" it with `values`,
                                do "nothing", or raise if `None`
        :param lookup_keys: all the lookup keys of the row, with table column
                            names as keys and row values as values
        """
        cls._check_lookup_keys(*lookup_keys.keys())
        values = values or {}
        insert = cls._get_insert()
        stmt = insert(cls).values(**lookup_keys, **values)
        if _on_conflict_do:
            on_conflict_do_method = cls._get_on_conflict_do()
            stmt = on_conflict_do_method(stmt, _on_conflict_do, values.keys())
        await session.execute(stmt)

    @classmethod
    async def create_multiple(
            cls,
            session: AsyncSession,
            /,
            values: list[dict],
            _on_conflict_do: on_conflict_opt = None,
    ) -> None:
        """Insert multiple rows in a single statement, optionally handling
        lookup keys conflicts.

        :param session: an AsyncSession instance
        :param values: a list of dicts, each one containing the values of a
                       row to insert. All the dicts should have the same keys
                       as the columns to update on conflict are inferred from
                       the first one.
        :param _on_conflict_do: what to do if a row with the same lookup keys
                                already exists: "update" it, do "nothing", or
                                raise if `None`
        """
        insert = cls._get_insert()
        stmt = insert(cls).values(values)
        if _on_conflict_do:
            on_conflict_do_method = cls._get_on_conflict_do()
            first = values if isinstance(values, dict) else values[0]
            stmt = on_conflict_do_method(stmt, _on_conflict_do, first.keys())
        await session.execute(stmt)

    @classmethod
    async def update_or_create(
            cls,
            session: AsyncSession,
            /,
            values: dict | None = None,
            **lookup_keys: lookup_keys_type,
    ) -> None:
        """Insert a row, or update it if a row with the same lookup keys
        already exists.

        :param session: an AsyncSession instance
        :param values: a dict with the non-lookup column names as keys and
                       the row values as values
        :param lookup_keys: all the lookup keys of the row, with table column
                            names as keys and row values as values
        """
        await cls.create(session, values=values, _on_conflict_do="update", **lookup_keys)

    @classmethod
    async def get_or_create(
            cls,
            session: AsyncSession,
            /,
            values: dict | None = None,
            **lookup_keys: lookup_keys_type,
    ) -> Self:
        """Return the row identified by the lookup keys, inserting it first
        if it does not exist. An existing row is left untouched.

        :param session: an AsyncSession instance
        :param values: a dict with the non-lookup column names as keys and
                       the values to use if the row is created
        :param lookup_keys: all the lookup keys of the row, with table column
                            names as keys and row values as values
        """
        await cls.create(session, values=values, _on_conflict_do="nothing", **lookup_keys)
        result = await cls.get(session, **lookup_keys)  # ty: ignore[invalid-argument-type]
        # `result` should not be `None` as it was created just before
        assert result is not None
        return result


class CacheMixin(UpsertCRUDMixin):
    _remove_expired_threshold: int = 10
    _remove_expired_tick: int = 0

    timestamp: Mapped[datetime] = mapped_column(UtcDateTime)

    @classmethod
    def get_ttl(cls) -> int:
        """Return data TTL in seconds"""
        raise NotImplementedError

    @classmethod
    async def insert_data(
            cls,
            session: AsyncSession,
            values: dict | list[dict]
    ) -> None:
        """Upsert data into the cache.

        Expired rows are removed every `_remove_expired_threshold` calls.

        :param session: an AsyncSession instance
        :param values: a dict or a list of dicts, each one containing the
                       values of a row to insert or update
        """
        cls._remove_expired_tick += 1
        if cls._remove_expired_tick >= cls._remove_expired_threshold:
            await cls.remove_expired(session)
            cls._remove_expired_tick = 0
        await cls.create_multiple(session, values=values, _on_conflict_do="update")  # ty: ignore[invalid-argument-type]

    @classmethod
    async def get_recent(
            cls,
            session: AsyncSession,
            **lookup_keys: list[lookup_keys_type] | lookup_keys_type | None,
    ) -> Sequence[Self]:
        """Return the rows that have not expired yet.

        :param session: an AsyncSession instance
        :param lookup_keys: a dict with table column names as keys and values
                            depending on the related column data type
        """
        stmt = cls._generate_get_query(**lookup_keys)  # ty: ignore[invalid-argument-type]
        time_limit = datetime.now(timezone.utc) - timedelta(seconds=cls.get_ttl())
        stmt = stmt.where(cls.timestamp > time_limit)
        result = await session.execute(stmt)
        return result.scalars().all()

    @classmethod
    async def remove_expired(cls, session: AsyncSession) -> None:
        """Delete the rows older than the TTL."""
        time_limit = datetime.now(timezone.utc) - timedelta(seconds=cls.get_ttl())
        stmt = delete(cls).where(cls.timestamp < time_limit)
        await session.execute(stmt)

    @classmethod
    async def clear(cls, session: AsyncSession) -> None:
        """Delete all the rows."""
        stmt = delete(cls)
        await session.execute(stmt)


class ArchivableMixin:
    _archive_column: str
    _archive_table: str

    if t.TYPE_CHECKING:
        __table__: Table
        id: Mapped[int]

    @classmethod
    def get_archive_table(cls) -> str:
        """Return the name of the table the data is archived to"""
        return cls._archive_table

    @classmethod
    def get_archive_column(cls) -> Column:
        """Return the column used to decide whether a row should be archived"""
        return cls.__table__.c[cls._archive_column]

    @classmethod
    def get_time_limit(cls) -> int | None:
        """Return data TTL before its archiving in days"""
        raise NotImplementedError
