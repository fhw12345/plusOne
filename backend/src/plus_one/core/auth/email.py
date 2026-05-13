"""Email delivery for magic-link.

In production: SMTP (settings.smtp_*).
In development: log the link to stdout (so you can copy it from the
console, no SMTP config needed).

Decision lives behind a Protocol so tests can inject a no-op or a
recording double.
"""

from __future__ import annotations

from typing import Protocol

import structlog

from plus_one.config import settings

logger = structlog.get_logger()


class EmailSender(Protocol):
    """Pluggable interface for sending the magic-link email."""

    async def send_magic_link(self, *, to: str, link: str) -> None: ...


class _ConsoleEmailSender:
    """Dev-only sender: logs the link instead of sending email.

    Lets you copy/paste the link from the dev console without standing
    up SMTP. NEVER use in production — the link bypasses the user's
    email and lands in your server logs.
    """

    async def send_magic_link(self, *, to: str, link: str) -> None:
        logger.warning(
            "magic_link_console_only",
            recipient=to,
            link=link,
            note="Dev-mode console sender — link is in this log line. "
            "Configure SMTP to send real email.",
        )


class _SmtpEmailSender:
    """Real SMTP sender. Stub for now — implementation in a follow-up batch.

    The real wiring needs aiosmtplib + an HTML template; deferred to keep
    this PR focused on auth correctness.
    """

    async def send_magic_link(self, *, to: str, link: str) -> None:
        raise NotImplementedError(
            "SMTP sender not implemented yet. Set APP_ENV=development to use "
            "the console sender, or wire up aiosmtplib in a follow-up PR."
        )


def get_email_sender() -> EmailSender:
    """Pick the sender based on ``APP_ENV``."""
    if settings.app_env == "production":
        return _SmtpEmailSender()
    return _ConsoleEmailSender()
