from datetime import datetime, timedelta, timezone

import pytest

from sqlalchemy_wrapper import AsyncSQLAlchemyWrapper

from ouranos.core.config.consts import SESSION_FRESHNESS, TOKEN_SUBS
from ouranos.core.database.models.app import User
from ouranos.core.exceptions import TokenError
from ouranos.core.utils import Tokenizer
from ouranos.web_server.user_session import (
    get_user_from_session_info, SessionInfo)

from tests.class_fixtures import UsersAware
from tests.data.auth import user


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


class TestSessionFreshness:
    """`SessionInfo.is_fresh` tells a recent login apart from an old one.

    It gates the actions that should require the user to have authenticated
    recently.
    """

    def test_new_session_is_fresh(self):
        assert SessionInfo(user_id=user.id).is_fresh

    def test_session_inside_the_window_is_fresh(self):
        issued_at = utc_now() - timedelta(seconds=SESSION_FRESHNESS - 60)

        assert SessionInfo(user_id=user.id, iat=issued_at).is_fresh

    def test_session_on_the_window_edge_is_not_fresh(self):
        issued_at = utc_now() - timedelta(seconds=SESSION_FRESHNESS)

        assert not SessionInfo(user_id=user.id, iat=issued_at).is_fresh

    def test_session_outside_the_window_is_not_fresh(self):
        issued_at = utc_now() - timedelta(seconds=SESSION_FRESHNESS + 60)

        assert not SessionInfo(user_id=user.id, iat=issued_at).is_fresh


class TestSessionToken:
    """Only a token minted by `SessionInfo.to_token()` can be used as a session.

    Every token is signed with the same key, and reset and confirmation tokens
    also carry a "user_id". Without the "session" subject check, a leaked reset
    link would log its holder in, and as it has no "iat" it would be always
    fresh and never older than `User.sessions_valid_from`.
    """

    def test_session_token_round_trips(self):
        session_info = SessionInfo(user_id=user.id)

        assert SessionInfo.from_token(session_info.to_token()) == session_info

    @pytest.mark.parametrize(
        "subject", [TOKEN_SUBS.RESET_PASSWORD, TOKEN_SUBS.CONFIRMATION])
    def test_other_token_is_rejected(self, subject: TOKEN_SUBS):
        # Same claims as `User.create_password_reset_token()` and
        # `User.create_confirmation_token()`
        token = Tokenizer.create_token(
            subject=subject.value, other_claims={"user_id": user.id})

        with pytest.raises(TokenError):
            SessionInfo.from_token(token)

    @pytest.mark.parametrize("missing", ["sub", "id", "user_id", "iat", "exp"])
    def test_token_missing_a_claim_is_rejected(self, missing: str):
        payload = SessionInfo(user_id=user.id).to_dict()
        payload["sub"] = TOKEN_SUBS.SESSION.value
        del payload[missing]

        with pytest.raises(TokenError):
            SessionInfo.from_token(Tokenizer.dumps(payload))


@pytest.mark.asyncio
class TestSessionValidityCutoff(UsersAware):
    """`User.sessions_valid_from` invalidates cookies that are still signed and unexpired.
    """

    async def test_session_issued_after_the_cutoff_is_accepted(
            self,
            db: AsyncSQLAlchemyWrapper,
    ):
        cutoff = utc_now() - timedelta(hours=1)
        async with db.scoped_session() as session:
            await User.update(
                session, user_id=user.id, values={"sessions_valid_from": cutoff})

        async with db.scoped_session() as session:
            resolved = await get_user_from_session_info(
                session,
                SessionInfo(user_id=user.id, iat=cutoff + timedelta(seconds=1)),
            )

        assert resolved.id == user.id

    async def test_session_issued_before_the_cutoff_is_rejected(
            self,
            db: AsyncSQLAlchemyWrapper,
    ):
        cutoff = utc_now() - timedelta(hours=1)
        async with db.scoped_session() as session:
            await User.update(
                session, user_id=user.id, values={"sessions_valid_from": cutoff})

        async with db.scoped_session() as session:
            resolved = await get_user_from_session_info(
                session,
                SessionInfo(user_id=user.id, iat=cutoff - timedelta(seconds=1))
            )

        assert resolved.is_anonymous

    async def test_session_issued_on_the_cutoff_second_is_accepted(
            self,
            db: AsyncSQLAlchemyWrapper,
    ):
        """The login a password reset triggers has to survive its own cutoff.

        `iat` is truncated to the second, so a session minted moments after the
        bump can carry the cutoff timestamp exactly. Rejecting it would log the
        user out of the session they just created.
        """
        cutoff = utc_now()
        async with db.scoped_session() as session:
            await User.update(
                session, user_id=user.id, values={"sessions_valid_from": cutoff})

        async with db.scoped_session() as session:
            resolved = await get_user_from_session_info(
                session,
                SessionInfo(user_id=user.id, iat=cutoff),
            )

        assert resolved.id == user.id

    async def test_no_session_info_is_anonymous(self, db: AsyncSQLAlchemyWrapper):
        async with db.scoped_session() as session:
            resolved = await get_user_from_session_info(session, None)

        assert resolved.is_anonymous
