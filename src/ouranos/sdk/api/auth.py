from __future__ import annotations

from datetime import datetime, timedelta
import typing as t

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from ouranos.core.config.consts import REGISTRATION_TOKEN_VALIDITY, TOKEN_SUBS
from ouranos.core.database.models.app import User, Role
from ouranos.core.utils import Tokenizer
from ouranos.sdk.api.exceptions import DuplicatedEntry, NoResultFound


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
            stmt = stmt.where(User.email == kwargs["email"])
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
        user_obj = await User.create(session, username, password, **kwargs)
        session.add(user_obj)
        await session.commit()
        return user_obj

    @staticmethod
    async def get(session: AsyncSession, user_id: int | str) -> User | None:
        stmt = (
            select(User)
            .where((User.id == user_id) | (User.username == user_id))
        )
        result = await session.execute(stmt)
        return result.scalars().one_or_none()

    @staticmethod
    async def get_by_telegram_id(
            session: AsyncSession,
            telegram_id: int
    ) -> User:
        stmt = select(User).where(User.telegram_chat_id == telegram_id)
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
    async def delete(session: AsyncSession, user_id: int | str):
        stmt = delete(User).where(
            (User.id == user_id)
            | (User.username == user_id)
        )
        await session.execute(stmt)


async def create_invitation_token(
        session: AsyncSession,
        role_name: str | None = None,
) -> str:
    if role_name is not None:
        if role_name != "default":
            stmt = select(Role).where(Role.name == role_name)
            result = await session.execute(stmt)
            role = result.scalars().first()
            if role is None:
                role_name = None
            else:
                stmt = select(Role).where(Role.default == True)  # noqa
                result = await session.execute(stmt)
                default_role = result.scalars().one()
                if role.name == default_role.name:
                    role_name = role.name
        else:
            role_name = None
    payload = {
        "sub": TOKEN_SUBS.REGISTRATION.value,
        "exp": datetime.utcnow() + timedelta(seconds=REGISTRATION_TOKEN_VALIDITY),
    }
    if role_name is not None:
        payload.update({"rle": role_name})
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