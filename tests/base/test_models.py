import pytest
from datetime import datetime, timezone
from unittest.mock import patch
from typing import Optional

from cachetools import TTLCache
from sqlalchemy import UniqueConstraint
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import desc, func

from sqlalchemy_wrapper import AsyncSQLAlchemyWrapper

from ouranos.core.database.models.abc import Base, CRUDMixin
from ouranos.core.database.models.caching import CachedCRUDMixin, create_hashable_key
from ouranos.core.database.models.types import UtcDateTime


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
    async def test_cache(self, db: AsyncSQLAlchemyWrapper):
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
            assert obj is not None
            assert obj.name == "Eve"

            # Verify it has been cached
            assert len(ModelCached._cache) == 1
            assert create_hashable_key(name="Eve") in ModelCached._cache

            # Verify no request is made
            with patch.object(CRUDMixin, "get") as mock_get:
                obj = await ModelCached.get(session, name="Eve")
                assert obj is not None
                assert obj.name == "Eve"
                assert mock_get.call_count == 0

            # Verify that update resets the cache
            await ModelCached.update(
                session,
                name="Eve",
                values={"age": 31},
            )
            assert len(ModelCached._cache) == 0

            # Recache the record
            await ModelCached.get(session, name="Eve")

            # Verify that delete resets the cache
            await ModelCached.delete(session, name="Eve")
            assert len(ModelCached._cache) == 0
