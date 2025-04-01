from datetime import datetime
from email.message import EmailMessage

import pytest

from sqlalchemy_wrapper import AsyncSQLAlchemyWrapper

from ouranos.core.database.models.app import User
from ouranos.core.email import Email, get_body_text, render_template

from tests.data.auth import user as user_


@pytest.mark.asyncio
async def test_rendering():
    subject = "A test"
    template = await render_template(
        "test", email_subject=subject, what="an email test")
    assert "<head>" in template
    assert "<body>" in template
    assert f"<title>{subject}</title>" in template
    assert "<p>Just an email test</p>" in template

    text = get_body_text(template)
    assert "<head>" not in text
    assert "<body>" not in text
    assert subject not in text
    assert "<p>Just an email test</p>" not in text
    assert "Just an email test" in text


@pytest.mark.asyncio
async def test_email():
    subject = "A test"
    html_template = await render_template(
        "test", email_subject=subject, what="an email test")
    body_text = get_body_text(html_template)

    sender = "gaiaweb@example.py"
    to = "definitelyARealPerson@example.py"

    email = Email(
        sender=sender,
        to=[to],
        subject=subject,
        body=body_text,
        html=html_template,
    )

    async with email.record_messages() as outbox:
        await email.send()
        msg = outbox[0]

        assert isinstance(msg, EmailMessage)
        assert msg._headers[0] == ("From", sender)
        assert msg._headers[1] == ("To", to)
        assert msg._headers[2] == ("Subject", subject)
        assert msg._headers[3][0] == "Message-ID"
        assert msg._headers[4] == ("MIME-Version", "1.0")

        assert len(msg._payload) == 2
        assert msg._payload[0]._headers[0] == ("Content-Type", 'text/plain; charset="utf-8"')
        assert msg._payload[0]._payload.strip() == body_text.strip()

        assert msg._payload[1]._headers[0] == ("Content-Type", 'text/html; charset="utf-8"')
        assert msg._payload[1]._payload.strip() == html_template.strip()


@pytest.mark.asyncio
async def test_invitation_email(db: AsyncSQLAlchemyWrapper):
    email_address = f"{user_.username}@fakemail.com"
    async with db.scoped_session() as session:
        async with Email.record_messages() as outbox:
            await User.send_invitation_email(session, email=email_address)

            msg = outbox.pop()

            assert isinstance(msg, EmailMessage)
            assert msg._headers[1] == ("To", email_address)
            assert msg._headers[2] == ("Subject", "Invitation to Gaia")

            assert len(msg._payload) == 2
            assert msg._payload[1]._headers[0] == ("Content-Type", 'text/html; charset="utf-8"')
            assert "use this registration token" in msg._payload[1]._payload


@pytest.mark.asyncio
async def test_confirm_email(db: AsyncSQLAlchemyWrapper):
    async with db.scoped_session() as session:
        user = await User.get(session, user_id=user_.id)
        async with Email.record_messages() as outbox:
            await user.send_confirmation_email(session)

            msg = outbox.pop()

            assert isinstance(msg, EmailMessage)
            assert msg._headers[1] == ("To", user.email)
            assert msg._headers[2] == ("Subject", "Welcome to Gaia")

            assert len(msg._payload) == 2
            assert msg._payload[1]._headers[0] == ("Content-Type", 'text/html; charset="utf-8"')
            assert f"Hej {user.username}" in msg._payload[1]._payload
            assert "In order to confirm your email address" in msg._payload[1]._payload


@pytest.mark.asyncio
async def test_reset_password_email(db: AsyncSQLAlchemyWrapper):
    async with db.scoped_session() as session:
        await User.update(
            session, user_id=user_.id, values={"confirmed_at": datetime.now()})
        user = await User.get(session, user_id=user_.id)
        async with Email.record_messages() as outbox:
            await user.send_reset_password_email(session)

            msg = outbox.pop()

            assert isinstance(msg, EmailMessage)
            assert msg._headers[1] == ("To", user.email)
            assert msg._headers[2] == ("Subject", "Reset your password")

            assert len(msg._payload) == 2
            assert msg._payload[1]._headers[0] == ("Content-Type", 'text/html; charset="utf-8"')
            assert f"Hej {user.username}" in msg._payload[1]._payload
            assert "We received a request to reset your password" in msg._payload[1]._payload
