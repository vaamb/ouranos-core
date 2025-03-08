from contextlib import asynccontextmanager
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import make_msgid
from typing import Iterator, Self

import aiosmtplib

from ouranos import current_app
from ouranos.core.email.templates import get_body_text, render_template


@dataclass
class Email:
    sender: str
    to: list[str]
    cc: list[str] | None = None
    bcc: list[str] | None = None
    subject: str = ""
    body: str | None = None
    html: str | None = None
    _outbox: list | None = None

    def make_msg(self) -> EmailMessage:
        msg = EmailMessage()
        msg["From"] = self.sender
        msg["To"] = ", ".join(self.to)
        if self.cc:
            msg["Cc"] = ", ".join(self.cc)
        if self.bcc:
            msg["Bcc"] = ", ".join(self.bcc)
        msg["Subject"] = self.subject
        msg["Message-ID"] = make_msgid()
        if self.body is not None:
            msg.set_content(self.body)
        if self.html is not None:
            msg.add_alternative(self.html, subtype="html")
        return msg

    async def send(
            self,
            *,
            hostname=None,
            port=None,
            username=None,
            password=None,
    ) -> None:
        hostname = hostname or current_app.config["MAIL_SERVER"]
        port = port or current_app.config["MAIL_PORT"]
        username = username or current_app.config["MAIL_USERNAME"]
        password = password or current_app.config["MAIL_PASSWORD"]

        if not all((hostname, port, username, password)):
            raise RuntimeError(
                "You either need to provide a `hostname`, `port`, `username` "
                "and `password` or to set the configuration variable 'MAIL_*' "
                "when using Ouranos in a production environment."
            )

        if current_app.config["TESTING"] and self._outbox is not None:
            self._outbox.append(self.make_msg())
            return

        await aiosmtplib.send(
            self.make_msg(),
            hostname=hostname,
            port=port,
            username=username,
            password=password,
            timeout=60,  # Default
            use_tls=current_app.config["MAIL_USE_TLS"],
            start_tls=not current_app.config["MAIL_USE_TLS"],
        )

    @asynccontextmanager
    async def record_messages(self) -> Iterator[list[Self]]:
        self._outbox = []

        yield self._outbox

        self._outbox = None
