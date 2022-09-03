from __future__ import annotations

from datetime import datetime, timedelta, timezone
import typing as t

from email_validator import validate_email
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from .exceptions import DuplicatedEntry, NoResultFound
from src.core.database.models.app import User, Role
from src.core.utils import Tokenizer


class user:
    @staticmethod
    async def create(
            session: AsyncSession,
            username: str,
            password: str,
            **kwargs
    ) -> User:
        error = []
        stmt = select(User).where(User.username == username)
        if "email" in kwargs:
            stmt = stmt.where(User.email == kwargs["mail"])
        if "telegram_id" in kwargs:
            stmt = stmt.where(User.telegram_chat_id == kwargs["telegram_id"])
        result = await session.execute(stmt)
        previous_user: User = result.scalars().first()
        if previous_user:
            if previous_user.username == username:
                error.append("username")
            if previous_user.email == kwargs.get("email", False):
                error.append("email")
            if previous_user.telegram_chat_id == kwargs.get("telegram_id", False):
                error.append("telegram_id")
            raise DuplicatedEntry(error)
        kwargs.update({"username": username})
        user = await User.create(session, **kwargs)
        user.set_password(password)
        session.add(user)
        await session.commit()
        return user

    @staticmethod
    async def get(session: AsyncSession, user: int | str) -> User:
        stmt = (
            select(User)
            .where((User.id == user) | (User.username == user))
        )
        result = await session.execute(stmt)
        return result.scalars().one_or_none()

    @staticmethod
    async def update(
            session: AsyncSession,
            user_id: int | str,
            new_info: dict
    ) -> t.Optional[list]:
        user_ = await user.get(session, user_id)
        if not user_:
            raise NoResultFound
        password = new_info.pop("password")
        if password:
            user_.set_password(password)
        wrong_attrs = []
        for info_name, info in new_info.items():
            try:
                setattr(user_, info_name, info)
            except AttributeError:
                wrong_attrs.append(info_name)
        session.add(user_)
        await session.commit()
        if wrong_attrs:
            return wrong_attrs

    @staticmethod
    async def delete(session: AsyncSession, user: int | str):
        stmt = delete(User).where((User.id == user) | (User.username == user))
        await session.execute(stmt)


async def create_invitation_token(
        session: AsyncSession,
        first_name: str = None,
        last_name: str = None,
        email_address: str = None,
        telegram_chat_id: int = None,
        role_name: t.Optional[str] = None,
        expiration_delay: timedelta = timedelta(days=7),
) -> str:
    email = None
    if email_address:
        email = validate_email(email_address.strip()).email
    assert email_address or telegram_chat_id
    role_name = role_name or "default"
    stmt = select(Role).where(Role.default == True)
    result = await session.execute(stmt)
    default_role = result.scalars().one()
    if role_name != "default":
        stmt = select(Role).where(Role.name == role_name)
        result = await session.execute(stmt)
        role = result.scalars().first()
        if not role:
            role = default_role
    else:
        role = default_role
    role_name = role.name
    if role_name == default_role.name:
        # simple users don't need to know they are simple
        role_name = None

    tkn_claims = {
        "fnm": first_name,
        "lnm": last_name,
        "eml": email,
        "tgm": telegram_chat_id,
        "rle": role_name,
        "exp": datetime.now(timezone.utc) + expiration_delay,
    }
    payload = {}
    for claim in tkn_claims:
        if tkn_claims[claim]:
            payload.update({claim: tkn_claims[claim]})
    return Tokenizer.dumps(payload)

"""
def send_invitation(invitation_jwt, db_session, mode="email"):
    decoded = jwt.decode(invitation_jwt, options={"verify_signature": False})
    firstname = decoded.get("fnm")
    exp_date = datetime.fromtimestamp(decoded.get("exp")).strftime("%A %d/%m")
    role = decoded.get("rle") or db_session.query(Role).filter_by(default=True
                                                                  ).one().name

    text = render_template("messages/../templates/messages/invitation.txt",
                           firstname=firstname, invitation_jwt=invitation_jwt,
                           exp_date=exp_date, role=role)
    html = render_template("messages/../templates/messages/invitation.html",
                           firstname=firstname, invitation_jwt=invitation_jwt,
                           exp_date=exp_date, role=role)
    if mode == "email":
        try:
            recipient = decoded["eml"]
        except KeyError:
            raise Exception("No email address present in the JSON Web Token")
        send_email(subject="Welcome to GAIApy",
                   sender=("GAIApy team", current_app.config["MAIL_USERNAME"]),
                   recipients=[recipient],
                   text_body=text,
                   html_body=html,
                   sync=True)
    elif mode == "telegram":
        try:
            recipient = decoded["tgm"]
        except KeyError:
            raise Exception("No email address present in the JSON Web Token")
"""