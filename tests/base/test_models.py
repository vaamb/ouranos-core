import pytest

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, mapped_column

from sqlalchemy_wrapper import AsyncSQLAlchemyWrapper

from ouranos.core.database.models.abc import Base, CRUDMixin


class TestModel(Base, CRUDMixin):
    __tablename__ = "tests"
    _lookup_keys = ["name"]

    name: Mapped[str] = mapped_column(primary_key=True)
    hobby: Mapped[str] = mapped_column()


@pytest.mark.asyncio
async def test_on_conflict(db: AsyncSQLAlchemyWrapper):
    await db.create_all()

    name = "John"

    # Create
    async with db.scoped_session() as session:
        await TestModel.create(session, name=name, values={"hobby": "reading"})

        model = await TestModel.get(session, name=name)
        assert model.name == name
        assert model.hobby == "reading"

    # Make sure it fails without the "_on_conflict_do" argument set
    async with db.scoped_session() as session:
        with pytest.raises(IntegrityError):
            await TestModel.create(
                session, name=name, values={"hobby": "gardening"})

    # On conflict do nothing
    async with db.scoped_session() as session:
        await TestModel.create(
            session, name=name, values={"hobby": "gardening"}, _on_conflict_do="nothing")

        model = await TestModel.get(session, name=name)
        assert model.name == name
        assert model.hobby == "reading"

    # On conflict update
    async with db.scoped_session() as session:
        await TestModel.create(
            session, name=name, values={"hobby": "gardening"}, _on_conflict_do="update")

        model = await TestModel.get(session, name=name)
        assert model.name == name
        assert model.hobby == "gardening"

    # On multiple update nothing
    async with db.scoped_session() as session:
        await TestModel.create_multiple(
            session,
            values=[
                {"name": name, "hobby": "gardening"},
                {"name": "Jane", "hobby": "coding"},
            ],
            _on_conflict_do="update",
        )

        model = await TestModel.get(session, name=name)
        assert model.name == name
        assert model.hobby == "gardening"

        model = await TestModel.get(session, name="Jane")
        assert model.name == "Jane"
        assert model.hobby == "coding"
