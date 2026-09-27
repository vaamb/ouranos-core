import pytest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch
from typing import Optional

from cachetools import TTLCache
from gaia_validators import missing
from sqlalchemy import insert, UniqueConstraint
from sqlalchemy.dialects.mysql import dialect as mysql_dialect, insert as mysql_insert
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import desc, func

from sqlalchemy_wrapper import AsyncSQLAlchemyWrapper

from ouranos.core.database.models.abc import Base, CRUDMixin
from ouranos.core.database.models.caching import CachedCRUDMixin, create_hashable_key
from ouranos.core.database.models.gaia import SensorDataCache
from ouranos.core.database.models.types import UtcDateTime
from ouranos.core.database.models.utils import HigherThan


class ModelSingleKey(Base, CRUDMixin):
    __tablename__ = "tests"
    _lookup_keys = ["name"]

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(unique=True)
    age: Mapped[int] = mapped_column()
    hobby: Mapped[Optional[str]] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=func.current_timestamp())


class ModelMultiKeys(Base, CRUDMixin):
    __tablename__ = "test_multi_lookup"
    _lookup_keys = ["firstname", "lastname"]

    id: Mapped[int] = mapped_column(primary_key=True)
    firstname: Mapped[str] = mapped_column()
    lastname: Mapped[str] = mapped_column()
    age: Mapped[int] = mapped_column()
    hobby: Mapped[Optional[str]] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=func.current_timestamp())

    __table_args__ = (
        UniqueConstraint(
            "firstname", "lastname",
            name="_uq_firstname_lastname"
        ),
    )


class ModelCached(ModelSingleKey, CachedCRUDMixin):
    _cache = TTLCache(maxsize=2, ttl=60)


class ModelNullable(Base, CRUDMixin):
    __tablename__ = "test_nullable"
    _lookup_keys = ["name"]

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(unique=True)
    hobby: Mapped[Optional[str]] = mapped_column(default=None)


_onupdate_calls: list[int] = []


def _counting_onupdate() -> int:
    # Callable `onupdate` whose return value changes on each evaluation, to
    # check it is recomputed for every statement rather than frozen
    _onupdate_calls.append(len(_onupdate_calls))
    return len(_onupdate_calls)


class ModelOnUpdate(Base, CRUDMixin):
    __tablename__ = "test_onupdate"
    _lookup_keys = ["name"]

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(unique=True)
    age: Mapped[int] = mapped_column()
    logged: Mapped[bool] = mapped_column(default=False, onupdate=lambda: False)
    counter: Mapped[int] = mapped_column(default=0, onupdate=_counting_onupdate)
    # A non-callable `onupdate` default, to cover the branch of
    # `_get_on_conflict_update_values()` that assigns `onupdate.arg` directly
    # rather than calling it.
    status: Mapped[str] = mapped_column(default="new", onupdate="refreshed")


class ModelPkOnlyLookup(Base, CRUDMixin):
    """No explicit `_lookup_keys` and no `unique=True` column: exercises the
    fallback of `_get_lookup_keys()` to `_get_unique_columns()`'s
    primary-key branch."""
    __tablename__ = "test_pk_only_lookup"

    id: Mapped[int] = mapped_column(primary_key=True)
    label: Mapped[str] = mapped_column()


class ModelBadLookupKey(Base, CRUDMixin):
    __tablename__ = "test_bad_lookup_key"
    _lookup_keys = ["not_a_column"]

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(unique=True)


class ModelNonUniqueLookupKey(Base, CRUDMixin):
    __tablename__ = "test_non_unique_lookup_key"
    _lookup_keys = ["age"]

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(unique=True)
    age: Mapped[int] = mapped_column()


class ModelDoubleUniqueConstraint(Base, CRUDMixin):
    __tablename__ = "test_double_unique_constraint"

    id: Mapped[int] = mapped_column(primary_key=True)
    a: Mapped[str] = mapped_column()
    b: Mapped[str] = mapped_column()
    c: Mapped[str] = mapped_column()
    d: Mapped[str] = mapped_column()

    __table_args__ = (
        UniqueConstraint("a", "b"),
        UniqueConstraint("c", "d"),
    )


class FakeNoUniqueModel(CRUDMixin):
    """Not a mapped SQLAlchemy class: only used to exercise the defensive
    "no unique constraint and no primary key" branch of
    `_get_unique_columns()`, which cannot occur on a real mapped model since
    SQLAlchemy refuses to map a class without a primary key."""
    __tablename__ = "fake_no_unique"


class ModelDialectSwitch(Base, CRUDMixin):
    """Dedicated model for mocking `_get_dialect()`. Never touched by a real
    DB query, so mutating its dialect-derived caches cannot affect other
    tests."""
    __tablename__ = "test_dialect_switch"
    _lookup_keys = ["name"]

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(unique=True)
    age: Mapped[int] = mapped_column()


@pytest.mark.asyncio
class TestCRUDMixinSingleKey:
    async def test_create_and_get(self, db: AsyncSQLAlchemyWrapper):
        # Test create and get
        async with db.scoped_session() as session:
            # Create a new record
            await ModelSingleKey.create(
                session,
                name="Alice",
                values={"hobby": "reading", "age": 20},
            )

            # Retrieve the record
            obj = await ModelSingleKey.get(session, name="Alice")
            assert obj is not None
            assert obj.name == "Alice"
            assert obj.age == 20
            assert obj.hobby == "reading"
            assert isinstance(obj.created_at, datetime)
            assert obj.created_at.tzinfo == timezone.utc

    async def test_create_missing_lookup_key(self, db: AsyncSQLAlchemyWrapper):
        async with db.scoped_session() as session:
            with pytest.raises(ValueError):
                await ModelSingleKey.create(
                    session,
                    values={"hobby": "reading", "age": 20},
                )

    async def test_to_dict_exclude(self, db: AsyncSQLAlchemyWrapper):
        async with db.scoped_session() as session:
            await ModelSingleKey.create(
                session, name="Dicty", values={"age": 99, "hobby": "chess"})
            obj = await ModelSingleKey.get(session, name="Dicty")

            full = obj.to_dict()
            assert full["age"] == 99
            assert full["hobby"] == "chess"

            partial = obj.to_dict(exclude=["age", "hobby"])
            assert "age" not in partial
            assert "hobby" not in partial
            assert partial["name"] == "Dicty"

    async def test_on_conflict_invalid_action_raises(
            self, db: AsyncSQLAlchemyWrapper):
        on_conflict_do = ModelSingleKey._get_on_conflict_do()
        stmt = insert(ModelSingleKey).values(name="InvalidAction", age=1)
        with pytest.raises(ValueError, match="Unknown on conflict action"):
            on_conflict_do(stmt, "bogus", [])

    async def test_unique_constraint(self, db: AsyncSQLAlchemyWrapper):
        # Test that the unique constraint works
        async with db.scoped_session() as session:
            # First create should work
            await ModelSingleKey.create(
                session, name="Dave", values={"age": 20},
            )

            # Second create with same firstname/lastname should fail
            with pytest.raises(IntegrityError):
                await ModelSingleKey.create(
                    session, name="Dave", values={"age": 42},
                )

    async def test_get_nonexistent(self, db: AsyncSQLAlchemyWrapper):
        async with db.scoped_session() as session:
            # Try to get a non-existent record
            obj = await ModelSingleKey.get(session, name="nonexistent")
            assert obj is None

    async def test_update(self, db: AsyncSQLAlchemyWrapper):
        # First create a record
        async with db.scoped_session() as session:
            await ModelSingleKey.create(
                session,
                name="Bob",
                values={"age": 30},
            )

        # Then update it
        async with db.scoped_session() as session:
            await ModelSingleKey.update(
                session,
                name="Bob",
                values={"hobby": "hiking"},
            )

            # Verify the update
            obj = await ModelSingleKey.get(session, name="Bob")
            assert obj.hobby == "hiking"

    async def test_delete(self, db: AsyncSQLAlchemyWrapper):
        # First create a record
        async with db.scoped_session() as session:
            await ModelSingleKey.create(
                session,
                name="Charlie",
                values={"age": 40},
            )

            # Verify it exists
            assert await ModelSingleKey.get(session, name="Charlie") is not None

            # Delete it
            await ModelSingleKey.delete(session, name="Charlie")

            # Verify it's gone
            assert await ModelSingleKey.get(session, name="Charlie") is None

    async def test_create_and_get_multiple(self, db: AsyncSQLAlchemyWrapper):
        await db.drop_all()
        await db.create_all()
        # Create multiple records
        test_data = [
            {"name": f"user_{i}", "age": 20 + i, "hobby": f"hobby_{i}"}
            for i in range(5)
        ]

        async with db.scoped_session() as session:
            # Create multiple records
            await ModelSingleKey.create_multiple(session, values=test_data)

            # Test get all
            all_objs = await ModelSingleKey.get_multiple(session)
            assert len(all_objs) == 5

            # Test with limit
            limited = await ModelSingleKey.get_multiple(session, limit=2)
            assert len(limited) == 2

            # Test with offset
            offset = await ModelSingleKey.get_multiple(session, offset=2)
            assert len(offset) == 3  # 5 total - 2 offset

            # Test with ordering

            ordered = await ModelSingleKey.get_multiple(
                session,
                order_by=desc(ModelSingleKey.hobby)
            )
            assert ordered[0].age == 24  # Should be highest age first

            # Test with filter
            filtered = await ModelSingleKey.get_multiple(session, age=22)
            assert len(filtered) == 1
            assert filtered[0].name == "user_2"

    async def test_on_conflict(self, db: AsyncSQLAlchemyWrapper):
        # Create
        async with db.scoped_session() as session:
            await ModelSingleKey.create(
                session,
                name="John",
                values={"age": 30, "hobby": "reading"},
            )

            model = await ModelSingleKey.get(session, name="John")
            assert model.name == "John"
            assert model.hobby == "reading"

        # Make sure it fails without the "_on_conflict_do" argument set
        async with db.scoped_session() as session:
            with pytest.raises(IntegrityError):
                await ModelSingleKey.create(
                    session, name="John", values={"age": 30, "hobby": "gardening"})

        # On conflict do nothing
        async with db.scoped_session() as session:
            await ModelSingleKey.create(
                session, name="John", values={"age": 30, "hobby": "gardening"}, _on_conflict_do="nothing")

            model = await ModelSingleKey.get(session, name="John")
            assert model.name == "John"
            assert model.hobby == "reading"

        # On conflict update
        async with db.scoped_session() as session:
            await ModelSingleKey.create(
                session, name="John", values={"age": 42, "hobby": "gardening"}, _on_conflict_do="update")

            model = await ModelSingleKey.get(session, name="John")
            assert model.name == "John"
            assert model.hobby == "gardening"

        # On multiple update nothing
        async with db.scoped_session() as session:
            await ModelSingleKey.create_multiple(
                session,
                values=[
                    {"name": "John", "age": 30, "hobby": "gardening"},
                    {"name": "Jane", "age": 30, "hobby": "coding"},
                ],
                _on_conflict_do="update",
            )

            model = await ModelSingleKey.get(session, name="John")
            assert model.name == "John"
            assert model.hobby == "gardening"

            model = await ModelSingleKey.get(session, name="Jane")
            assert model.name == "Jane"
            assert model.hobby == "coding"

    async def test_on_conflict_update_without_values(self, db: AsyncSQLAlchemyWrapper):
        # An "update" with nothing to update must not fail (SQLAlchemy refuses
        # an empty update mapping) and must behave like a "nothing"
        async with db.scoped_session() as session:
            await ModelNullable.create(
                session, name="Jim", values={"hobby": "reading"})

        async with db.scoped_session() as session:
            await ModelNullable.update_or_create(session, name="Jim")

            model = await ModelNullable.get(session, name="Jim")
            assert model.hobby == "reading"

        # It must still insert a missing row
        async with db.scoped_session() as session:
            await ModelNullable.update_or_create(session, name="Joe")

            model = await ModelNullable.get(session, name="Joe")
            assert model is not None
            assert model.hobby is None

    async def test_update_all_values_missing_is_noop(self, db: AsyncSQLAlchemyWrapper):
        # `missing` entries are filtered out of `values`; if none remain, the
        # update must be skipped entirely rather than issuing an empty
        # `UPDATE ... SET` statement
        async with db.scoped_session() as session:
            await ModelSingleKey.create(
                session, name="Untouched", values={"age": 5})

            await ModelSingleKey.update(
                session, name="Untouched", values={"age": missing})

            model = await ModelSingleKey.get(session, name="Untouched")
            assert model.age == 5

    async def test_get_multiple_ignores_none_valued_lookup_key(
            self, db: AsyncSQLAlchemyWrapper):
        await db.drop_all()
        await db.create_all()
        test_data = [
            {"name": f"mod_{i}", "age": 20 + i, "hobby": f"hobby_{i}"}
            for i in range(3)
        ]
        async with db.scoped_session() as session:
            await ModelSingleKey.create_multiple(session, values=test_data)

            # A `None`-valued lookup key is ignored, i.e. no filter is applied
            # for it, rather than matching rows where the column is NULL
            all_objs = await ModelSingleKey.get_multiple(session, age=None)
            assert len(all_objs) == 3

    async def test_get_multiple_list_value_uses_in_filter(
            self, db: AsyncSQLAlchemyWrapper):
        await db.drop_all()
        await db.create_all()
        test_data = [
            {"name": f"mod_{i}", "age": 20 + i, "hobby": f"hobby_{i}"}
            for i in range(3)
        ]
        async with db.scoped_session() as session:
            await ModelSingleKey.create_multiple(session, values=test_data)

            subset = await ModelSingleKey.get_multiple(
                session, name=["mod_0", "mod_2"])
            assert {obj.name for obj in subset} == {"mod_0", "mod_2"}

    async def test_get_multiple_stmt_modifier(self, db: AsyncSQLAlchemyWrapper):
        await db.drop_all()
        await db.create_all()
        test_data = [
            {"name": f"mod_{i}", "age": 20 + i, "hobby": f"hobby_{i}"}
            for i in range(3)
        ]
        async with db.scoped_session() as session:
            await ModelSingleKey.create_multiple(session, values=test_data)

            above = await ModelSingleKey.get_multiple(session, age=HigherThan(20))
            assert {obj.age for obj in above} == {21, 22}


@pytest.mark.asyncio
class TestGetOrCreate:
    async def test_creates_when_missing(self, db: AsyncSQLAlchemyWrapper):
        async with db.scoped_session() as session:
            obj = await ModelSingleKey.get_or_create(
                session, name="Fresh", values={"age": 25})
            assert obj.name == "Fresh"
            assert obj.age == 25

    async def test_returns_existing_without_overwriting(
            self, db: AsyncSQLAlchemyWrapper):
        async with db.scoped_session() as session:
            await ModelSingleKey.create(
                session, name="Existing", values={"age": 10})

            obj = await ModelSingleKey.get_or_create(
                session, name="Existing", values={"age": 99})
            assert obj.age == 10


@pytest.mark.asyncio
class TestCRUDMixinOnUpdate:
    async def test_onupdate_refreshed_on_conflict(self, db: AsyncSQLAlchemyWrapper):
        async with db.scoped_session() as session:
            await ModelOnUpdate.create(session, name="John", values={"age": 30})
            await ModelOnUpdate.update(session, name="John", values={"logged": True})

            model = await ModelOnUpdate.get(session, name="John")
            assert model.logged is True

        # A new insert for the same lookup key resets `logged` even though it
        # was not part of the supplied values
        async with db.scoped_session() as session:
            await ModelOnUpdate.update_or_create(
                session, name="John", values={"age": 31})

            model = await ModelOnUpdate.get(session, name="John")
            assert model.age == 31
            assert model.logged is False

    async def test_explicit_value_wins_over_onupdate(self, db: AsyncSQLAlchemyWrapper):
        async with db.scoped_session() as session:
            await ModelOnUpdate.create(session, name="Jane", values={"age": 30})

        # A value explicitly supplied must not be overridden by the `onupdate`
        async with db.scoped_session() as session:
            await ModelOnUpdate.update_or_create(
                session, name="Jane", values={"age": 31, "logged": True})

            model = await ModelOnUpdate.get(session, name="Jane")
            assert model.age == 31
            assert model.logged is True

        async with db.scoped_session() as session:
            await ModelOnUpdate.create_multiple(
                session,
                values=[{"name": "Jane", "age": 32, "logged": True}],
                _on_conflict_do="update",
            )

            model = await ModelOnUpdate.get(session, name="Jane")
            assert model.age == 32
            assert model.logged is True

    async def test_callable_onupdate_evaluated_per_statement(
            self, db: AsyncSQLAlchemyWrapper):
        async with db.scoped_session() as session:
            await ModelOnUpdate.create(session, name="Jack", values={"age": 30})

        counters = []
        for _ in range(2):
            async with db.scoped_session() as session:
                await ModelOnUpdate.update_or_create(
                    session, name="Jack", values={"age": 31})

                model = await ModelOnUpdate.get(session, name="Jack")
                counters.append(model.counter)

        # The callable must be evaluated again for each conflicting statement,
        # not frozen at the value computed when the "on conflict" closure
        # was first built
        assert counters[0] != counters[1]

    async def test_static_onupdate_value_used_on_conflict(
            self, db: AsyncSQLAlchemyWrapper):
        # A non-callable `onupdate` default (`status`) must be assigned
        # directly (`onupdate.arg`), not called, and still be refreshed on
        # conflict even though it is not part of the supplied values
        async with db.scoped_session() as session:
            await ModelOnUpdate.create(session, name="Jill", values={"age": 30})

            model = await ModelOnUpdate.get(session, name="Jill")
            assert model.status == "new"

        async with db.scoped_session() as session:
            await ModelOnUpdate.update_or_create(
                session, name="Jill", values={"age": 31})

            model = await ModelOnUpdate.get(session, name="Jill")
            assert model.status == "refreshed"


class TestGetUniqueColumns:
    def test_primary_key_fallback(self):
        # No `unique=True` column: falls back to the primary key
        assert ModelPkOnlyLookup._get_unique_columns() == ["id"]

    def test_double_unique_constraint_raises(self):
        with pytest.raises(ValueError, match="single `UniqueConstraint`"):
            ModelDoubleUniqueConstraint._get_unique_columns()

    def test_no_unique_no_primary_key_raises(self):
        # A real mapped model cannot reach this branch (SQLAlchemy refuses to
        # map a class without a primary key), so the columns are faked
        fake_columns = [SimpleNamespace(name="a", unique=False, primary_key=False)]
        with patch(
                "ouranos.core.database.models.abc.class_mapper",
                return_value=SimpleNamespace(columns=fake_columns),
        ):
            with pytest.raises(ValueError, match="no unique constraint"):
                FakeNoUniqueModel._get_unique_columns()


class TestValidateLookupKeys:
    def test_lookup_key_not_a_column_raises(self):
        with pytest.raises(ValueError, match="is not a column"):
            ModelBadLookupKey._get_lookup_keys()

    def test_lookup_key_not_unique_raises(self):
        with pytest.raises(ValueError, match="no unique constraint"):
            ModelNonUniqueLookupKey._get_lookup_keys()


@pytest.mark.asyncio
class TestAutoLookupKeys:
    async def test_crud_without_explicit_lookup_keys(self, db: AsyncSQLAlchemyWrapper):
        # `_lookup_keys` is not set on `ModelPkOnlyLookup`: `_get_lookup_keys()`
        # must fall back to the unique columns (here, the primary key)
        assert ModelPkOnlyLookup._get_lookup_keys() == ["id"]

        async with db.scoped_session() as session:
            await ModelPkOnlyLookup.create(session, id=1, values={"label": "a"})

            obj = await ModelPkOnlyLookup.get(session, id=1)
            assert obj.label == "a"

            await ModelPkOnlyLookup.update(session, id=1, values={"label": "b"})
            obj = await ModelPkOnlyLookup.get(session, id=1)
            assert obj.label == "b"

            await ModelPkOnlyLookup.delete(session, id=1)
            assert await ModelPkOnlyLookup.get(session, id=1) is None


class TestOnConflictDialects:
    """`ModelDialectSwitch` is never used with a real DB query, so mocking
    `_get_dialect()` and mutating its dialect-derived caches cannot leak into
    other tests."""

    def teardown_method(self):
        # Reset the caches populated by `_get_on_conflict_do()`/`_get_insert()`
        # so the mocked dialect never leaks between tests
        ModelDialectSwitch._dialect = None
        ModelDialectSwitch._insert = None
        ModelDialectSwitch._on_conflict_do = None

    def test_get_insert_mysql_dialect(self):
        with patch.object(ModelDialectSwitch, "_get_dialect", return_value="mysql"):
            assert ModelDialectSwitch._get_insert() is mysql_insert

    def test_get_insert_postgresql_dialect(self):
        with patch.object(
                ModelDialectSwitch, "_get_dialect", return_value="postgresql"):
            assert ModelDialectSwitch._get_insert() is pg_insert

    def test_get_insert_unknown_dialect_falls_back_to_generic(self):
        with patch.object(
                ModelDialectSwitch, "_get_dialect", return_value="oracle"):
            assert ModelDialectSwitch._get_insert() is insert

    def test_mysql_on_conflict_do(self):
        with patch.object(ModelDialectSwitch, "_get_dialect", return_value="mysql"):
            on_conflict_do = ModelDialectSwitch._get_on_conflict_do()

        def on_duplicate_clause(action: str, columns: list[str]) -> str:
            stmt = mysql_insert(ModelDialectSwitch).values(name="X", age=1)
            stmt = on_conflict_do(stmt, action, columns)
            compiled = str(stmt.compile(dialect=mysql_dialect()))
            _, _, clause = compiled.partition("ON DUPLICATE KEY UPDATE ")
            return clause

        stmt = mysql_insert(ModelDialectSwitch).values(name="X", age=1)
        with pytest.raises(ValueError, match="Unknown on conflict action"):
            on_conflict_do(stmt, "bogus", ["age"])

        # "nothing" with no columns to update assigns the lookup column to
        # itself, rather than to `stmt.inserted`, so that a conflict on a
        # different unique index does not overwrite the lookup key
        assert on_duplicate_clause("nothing", []) == \
               "name = test_dialect_switch.name"

        # "update" refreshes the non-lookup columns supplied to `create`
        assert on_duplicate_clause("update", ["age"]) == "age = VALUES(age)"

    def test_unsupported_dialect_warns_and_passes_statement_through(self):
        with patch.object(
                ModelDialectSwitch, "_get_dialect", return_value="oracle"):
            with pytest.warns(UserWarning, match="not yet supported"):
                on_conflict_do = ModelDialectSwitch._get_on_conflict_do()

        stmt = insert(ModelDialectSwitch).values(name="X", age=1)
        assert on_conflict_do(stmt, "nothing", []) is stmt

        with pytest.raises(ValueError, match="Unknown on conflict action"):
            on_conflict_do(stmt, "bogus", [])


@pytest.mark.asyncio
class TestSensorDataCacheOnUpdate:
    async def test_logged_resets_on_new_data(self, db: AsyncSQLAlchemyWrapper):
        values = {
            "ecosystem_uid": "ecosystem_uid",
            "sensor_uid": "sensor_uid",
            "measure": "measure",
            "value": 1.0,
            "timestamp": datetime.now(timezone.utc),
        }
        async with db.scoped_session() as session:
            await SensorDataCache.insert_data(session, values)
            await session.commit()

        async with db.scoped_session() as session:
            recent = await SensorDataCache.get_recent(session, logged=False)
            assert len(recent) == 1
            await SensorDataCache.update_multiple(
                session, values=[{"id": recent[0].id, "logged": True}])
            await session.commit()

        async with db.scoped_session() as session:
            recent = await SensorDataCache.get_recent(session, logged=False)
            assert len(recent) == 0

        # New reading comes in for the same sensor/measure: `logged` must reset
        async with db.scoped_session() as session:
            await SensorDataCache.insert_data(session, {**values, "value": 2.0})
            await session.commit()

        async with db.scoped_session() as session:
            recent = await SensorDataCache.get_recent(session, logged=False)
            assert len(recent) == 1, (
                "`logged` was not reset to `False` when new data was cached "
                "again for the same sensor/measure"
            )


@pytest.mark.asyncio
class TestCRUDMixinMultiKeys:
    async def test_create_and_get(self, db: AsyncSQLAlchemyWrapper):
        # Test create and get with multiple lookup keys
        async with db.scoped_session() as session:
            # Create a new record
            await ModelMultiKeys.create(
                session,
                firstname="John",
                lastname="Doe",
                values={"age": 30, "hobby": "coding"},
            )

            # Retrieve the record
            obj = await ModelMultiKeys.get(
                session,
                firstname="John",
                lastname="Doe",
            )
            assert obj is not None
            assert obj.firstname == "John"
            assert obj.lastname == "Doe"
            assert obj.age == 30
            assert obj.hobby == "coding"
            assert isinstance(obj.created_at, datetime)
            assert obj.created_at.tzinfo == timezone.utc

    async def test_create_missing_lookup_key(self, db: AsyncSQLAlchemyWrapper):
        async with db.scoped_session() as session:
            with pytest.raises(ValueError):
                await ModelMultiKeys.create(
                    session,
                    firstname="John",
                    values={"hobby": "coding", "age": 30},
                )

    async def test_update(self, db: AsyncSQLAlchemyWrapper):
        # First create a record
        async with db.scoped_session() as session:
            await ModelMultiKeys.create(
                session,
                firstname="Jane",
                lastname="Smith",
                values={"age": 30},
            )

        # Then update it
        async with db.scoped_session() as session:
            await ModelMultiKeys.update(
                session,
                firstname="Jane",
                lastname="Smith",
                values={"age": 28},
            )

            # Verify the update
            obj = await ModelMultiKeys.get(
                session,
                firstname="Jane",
                lastname="Smith",
            )
            assert obj.age == 28

    async def test_delete(self, db: AsyncSQLAlchemyWrapper):
        # First create a record
        async with db.scoped_session() as session:
            await ModelMultiKeys.create(
                session,
                firstname="charlie",
                lastname="brown",
                values={"age": 40},
            )

            # Verify it exists
            assert await ModelMultiKeys.get(
                session,
                firstname="charlie",
                lastname="brown",
            ) is not None

            # Delete it
            await ModelMultiKeys.delete(session, firstname="charlie", lastname="brown", )

            # Verify it's gone
            assert await ModelMultiKeys.get(
                session,
                firstname="charlie",
                lastname="brown",
            ) is None


@pytest.mark.asyncio
class TestCachedCRUDMixin:
    async def test_cache_exists(self, db: AsyncSQLAlchemyWrapper):
        async with db.scoped_session() as session:
            # Create a new record
            await ModelCached.create(
                session,
                name="Eve",
                values={"age": 30, "hobby": "coding"},
            )
            assert len(ModelCached._cache) == 0

            # Retrieve the record
            obj = await ModelCached.get(session, name="Eve")
            assert obj.name == "Eve"

            # Verify it has been cached
            assert len(ModelCached._cache) == 1
            key = create_hashable_key(name="Eve")
            assert key in ModelCached._cache
            assert ModelCached._cache[key] == obj

            # Verify "get" method isn't called when the object is cached
            with patch.object(CRUDMixin, "get") as mock_get:
                await ModelCached.get(session, name="Eve")
                assert mock_get.call_count == 0

            await ModelCached.delete(session, name="Eve")

    async def test_create_on_conflict_update_invalidates_cache(
            self,
            db: AsyncSQLAlchemyWrapper,
    ):
        async with db.scoped_session() as session:
            await ModelCached.create(session, name="Alice", values={"age": 30})
            await ModelCached.get(session, name="Alice")
            key = create_hashable_key(name="Alice")
            assert key in ModelCached._cache

            await ModelCached.create(
                session, name="Alice", values={"age": 31}, _on_conflict_do="update")

            assert key not in ModelCached._cache

            obj = await ModelCached.get(session, name="Alice")
            assert obj.name == "Alice"
            assert obj.age == 31

            await ModelCached.delete(session, name="Alice")

    async def test_update_invalidates_cache(self, db: AsyncSQLAlchemyWrapper):
        async with db.scoped_session() as session:
            await ModelCached.create(session, name="Eve", values={"age": 40})
            await ModelCached.get(session, name="Eve")
            key = create_hashable_key(name="Eve")
            assert key in ModelCached._cache

            # Verify that update resets the cache
            await ModelCached.update(session, name="Eve", values={"age": 31})
            assert key not in ModelCached._cache

            # Recache the record
            obj = await ModelCached.get(session, name="Eve")
            assert key in ModelCached._cache
            assert obj.age == 31

            await ModelCached.delete(session, name="Eve")

    async def test_delete_invalidates_cache(self, db: AsyncSQLAlchemyWrapper):
        async with db.scoped_session() as session:
            await ModelCached.create(session, name="Eve", values={"age": 40})
            await ModelCached.get(session, name="Eve")
            key = create_hashable_key(name="Eve")
            assert key in ModelCached._cache

            # Verify that update resets the cache
            await ModelCached.delete(session, name="Eve")
            assert key not in ModelCached._cache

            obj = await ModelCached.get(session, name="Eve")
            assert obj is None
            # Empty results are cached
            assert key in ModelCached._cache

    async def test_clear_cache_manual_invalidation(self, db: AsyncSQLAlchemyWrapper):
        async with db.scoped_session() as session:
            await ModelCached.create(session, name="Frank", values={"age": 22})
            await ModelCached.get(session, name="Frank")
            key = create_hashable_key(name="Frank")
            assert key in ModelCached._cache

            ModelCached.clear_cache(name="Frank")
            assert key not in ModelCached._cache

            await ModelCached.delete(session, name="Frank")

    async def test_clear_cache_missing_lookup_key_raises(self, db: AsyncSQLAlchemyWrapper):
        with pytest.raises(ValueError, match="all the lookup keys"):
            ModelCached.clear_cache()

    async def test_create_multiple_invalidates_cache(self, db: AsyncSQLAlchemyWrapper):
        async with db.scoped_session() as session:
            await ModelCached.create(session, name="Gina", values={"age": 40})
            await ModelCached.get(session, name="Gina")
            key = create_hashable_key(name="Gina")
            assert key in ModelCached._cache

            await ModelCached.create_multiple(
                session,
                values=[{"name": "Gina", "age": 41, "hobby": "yoga"}],
                _on_conflict_do="update",
            )
            assert key not in ModelCached._cache

            obj = await ModelCached.get(session, name="Gina")
            assert obj.age == 41

            await ModelCached.delete(session, name="Gina")

    async def test_update_multiple_invalidates_cache(self, db: AsyncSQLAlchemyWrapper):
        async with db.scoped_session() as session:
            await ModelCached.create(session, name="Hank", values={"age": 50})
            cached_obj = await ModelCached.get(session, name="Hank")
            key = create_hashable_key(name="Hank")
            assert key in ModelCached._cache

            await ModelCached.update_multiple(
                session, values=[{"id": cached_obj.id, "name": "Hank", "age": 51}])
            assert key not in ModelCached._cache

            obj = await ModelCached.get(session, name="Hank")
            assert obj.age == 51

            await ModelCached.delete(session, name="Hank")

    async def test_get_with_offset_limit_or_order_by_bypasses_cache(
            self,
            db: AsyncSQLAlchemyWrapper,
    ):
        async with db.scoped_session() as session:
            await ModelCached.create(session, name="Ian", values={"age": 60})

            with patch.object(ModelCached, "_cached_get") as mock_cached_get:
                obj = await ModelCached.get(session, name="Ian", limit=1)
                assert obj is not None
                assert obj.name == "Ian"
                assert mock_cached_get.call_count == 0

            # Not cached, since the call above bypassed `_cached_get`
            assert create_hashable_key(name="Ian") not in ModelCached._cache

            await ModelCached.delete(session, name="Ian")
