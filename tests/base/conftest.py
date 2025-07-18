import pytest
import pytest_asyncio

from sqlalchemy_wrapper import AsyncSQLAlchemyWrapper

from ouranos.core.database.models.app import User
from ouranos.sdk.plugin import Plugin
from ouranos.sdk.tests.plugin import DummyFunctionality

from tests.data.auth import user


@pytest_asyncio.fixture(scope="module", autouse=True)
async def users(db: AsyncSQLAlchemyWrapper):
    async with db.scoped_session() as session:
        user_info = {
            "id": user.id,
            "username": user.username,
            "password": user.password,
            "email": f"{user.username}@fakemail.com",
            "firstname": user.firstname,
            "lastname": user.lastname,
            "role": user.role.value,
        }
        await User.create(session, values=user_info)


@pytest.fixture(scope="function")
def dummy_plugin():
    return Plugin(
        functionality=DummyFunctionality,
        name="dummy-plugin",
    )
