from email.message import EmailMessage

import pytest

from ouranos.core.email import Email, get_body_text, render_template


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
