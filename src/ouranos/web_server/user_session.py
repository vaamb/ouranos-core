from __future__ import annotations

from datetime import datetime, timedelta, timezone
from secrets import token_urlsafe
from typing import Self

from pydantic import BaseModel, ValidationError, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ouranos.core.config.consts import SESSION_FRESHNESS, SESSION_TOKEN_VALIDITY
from ouranos.core.database.models.app import anonymous_user, User, UserMixin
from ouranos.core.exceptions import TokenError
from ouranos.core.utils import Tokenizer


def _create_session_id() -> str:
    return token_urlsafe(32)


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _get_exp_dt() -> datetime:
    return _now() + timedelta(seconds=SESSION_TOKEN_VALIDITY)


class SessionInfo(BaseModel):
    id: str = Field(default_factory=_create_session_id)
    user_id: int
    iat: datetime = Field(default_factory=_now)
    exp: datetime = Field(default_factory=_get_exp_dt)
    remember: bool = False

    @property
    def is_fresh(self) -> bool:
        time_limit = (
            datetime.now(timezone.utc).replace(microsecond=0)
            - timedelta(seconds=SESSION_FRESHNESS)
        )
        return self.iat > time_limit

    def refresh_iat(self) -> None:
        self.iat = _now()

    def refresh_exp(self) -> None:
        self.exp = _get_exp_dt()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "iat": self.iat,
            "exp": self.exp,
            "remember": self.remember is True,
        }

    def to_token(self) -> str:
        return Tokenizer.dumps(self.to_dict())

    @classmethod
    def from_token(
            cls,
            token: str,
    ) -> Self:
        try:
            return cls(**Tokenizer.loads(token))
        except ValidationError:
            raise TokenError


async def get_user(
        db_session: AsyncSession,
        user_id: int | str,
) -> UserMixin:
    if isinstance(user_id, int):
        user = await User.get(db_session, user_id)
    else:
        user = await User.get_by(db_session, username=user_id)
    if user is None or not user.active:
        return anonymous_user
    return user


async def get_user_from_session_info(
        db_session: AsyncSession,
        session_info: SessionInfo | None,
) -> UserMixin:
    if session_info is None:
        return anonymous_user
    user = await get_user(db_session, session_info.user_id)
    if user.is_anonymous:
        return user
    assert isinstance(user, User)
    # Check that the token was emitted after the validation cutoff
    if session_info.iat < user.sessions_valid_from:
        return anonymous_user
    return user
