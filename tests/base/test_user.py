import pytest

from sqlalchemy_wrapper import AsyncSQLAlchemyWrapper

from ouranos.core.database.models.app import User


@pytest.mark.asyncio
class TestUser:
    async def test_user(self, db: AsyncSQLAlchemyWrapper):
        async with db.scoped_session() as session:
            await User.create(
                session,
                values={
                    "username": "testUser",
                    "email": "testUser@fakemail.com",
                    "password": "Password1!",
                }
            )

            user = await User.get_by(session, username="testUser")
            assert user is not None

            user = await User.get_by(session, email="testUser@fakemail.com")
            assert user is not None

            user_id = user.id
            user = await User.get(session, user_id)
            assert user is not None

            await User.delete(session, user_id=user_id)
            user = await User.get(session, user_id)
            assert user.active is False

            user = await User.get_by(session, username="testUser", active=True)
            assert user is None

            user = await User.get(session, 42)
            assert user is None
