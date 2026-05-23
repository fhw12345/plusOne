"""SMTP email sender (batch-2m).

Replaces the dev-only console sender. Reads credentials from
:mod:`plus_one.config` (``SMTP_HOST`` / ``SMTP_PORT`` / ``SMTP_USE_SSL``
/ ``SMTP_USER`` / ``SMTP_PASSWORD`` / ``SMTP_FROM`` /
``SMTP_FROM_NAME``).

Public API:

  * :func:`send_email` — generic multipart/alternative sender.
  * :func:`send_code_email` — the batch-2m verify/login template.
  * :class:`EmailSendError` — raised on any underlying SMTP failure;
    callers translate to HTTP 503 ``email_sender_unavailable``.

Never logs ``SMTP_PASSWORD`` or the raw code.
"""

from __future__ import annotations

import logging
from email.message import EmailMessage

import aiosmtplib

from plus_one.config import settings

logger = logging.getLogger(__name__)


class EmailSendError(RuntimeError):
    """SMTP send failed — wrap the underlying exception."""


def _build_message(
    *,
    to: str,
    subject: str,
    body_text: str,
    body_html: str | None,
) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = f"{settings.smtp_from_name} <{settings.smtp_from}>"
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body_text)
    if body_html is not None:
        msg.add_alternative(body_html, subtype="html")
    return msg


async def send_email(
    *,
    to: str,
    subject: str,
    body_text: str,
    body_html: str | None = None,
) -> None:
    """Send a single email via the configured SMTP server.

    Picks SSL vs STARTTLS based on ``SMTP_USE_SSL``:
      * True  -> implicit TLS (port 465 typical, ``use_tls=True``)
      * False -> STARTTLS (port 587 typical, ``start_tls=True``)
    """
    if settings.allow_console_email_sender and not settings.smtp_host:
        # Dev/CI fallback: write a redacted line to logs instead of sending.
        # Code retrieval for e2e goes through /api/auth/dev/last-code, which
        # reads from the DB, so the body content is intentionally NOT logged.
        logger.info("console_email_sent to=%s subject=%s", to, subject)
        return

    if not settings.smtp_host:
        raise EmailSendError("smtp_host not configured")

    msg = _build_message(to=to, subject=subject, body_text=body_text, body_html=body_html)

    try:
        if settings.smtp_use_ssl:
            await aiosmtplib.send(
                msg,
                hostname=settings.smtp_host,
                port=settings.smtp_port,
                username=settings.smtp_user,
                password=settings.smtp_password,
                use_tls=True,
            )
        else:
            await aiosmtplib.send(
                msg,
                hostname=settings.smtp_host,
                port=settings.smtp_port,
                username=settings.smtp_user,
                password=settings.smtp_password,
                start_tls=True,
            )
    except Exception as exc:
        # Don't log the password — just the host + recipient + error type.
        logger.warning(
            "smtp_send_failed host=%s to=%s error=%s",
            settings.smtp_host,
            to,
            type(exc).__name__,
        )
        raise EmailSendError(str(exc)) from exc

    logger.info("smtp_send_ok host=%s to=%s", settings.smtp_host, to)


_SUBJECT = "your code, pinned"

_PLAIN_TEMPLATE = """hello —

here's the code: {code}

it's good for 10 minutes. one use, then it's gone.

if this wasn't you, ignore this — nothing happens until someone types it in.

— plus one
"""

_HTML_TEMPLATE = """<!doctype html>
<html><body style="background:#f5efe1;color:#221c14;font-family:Georgia,serif;padding:24px;">
  <p>hello —</p>
  <p>here's the code:</p>
  <p style="font-family:'Courier New',monospace;font-size:32px;letter-spacing:6px;padding:14px 18px;background:#faf5e9;border:1px dashed #b09472;display:inline-block;">{code}</p>
  <p>it's good for 10 minutes. one use, then it's gone.</p>
  <p style="color:#7a6a52;font-size:13px;">if this wasn't you, ignore this — nothing happens until someone types it in.</p>
  <p>— plus one</p>
</body></html>
"""


async def send_code_email(*, to: str, code: str) -> None:
    """Send the verify/login code email (PRD §9 template)."""
    await send_email(
        to=to,
        subject=_SUBJECT,
        body_text=_PLAIN_TEMPLATE.format(code=code),
        body_html=_HTML_TEMPLATE.format(code=code),
    )
