"""Tests for the email sender selector + console sender."""

from __future__ import annotations

import pytest

from plus_one.config import settings
from plus_one.core.auth.email import (
    _ConsoleEmailSender,
    _SmtpEmailSender,
    get_email_sender,
)


@pytest.mark.unit
def test_get_sender_default_is_smtp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Default selector returns SMTP sender — staging or anything else
    that forgets to wire SMTP gets a loud failure on first send rather
    than silently leaking links into logs (reviewer F2)."""
    monkeypatch.setattr(settings, "allow_console_email_sender", False)
    sender = get_email_sender()
    assert isinstance(sender, _SmtpEmailSender)


@pytest.mark.unit
def test_get_sender_returns_console_only_with_explicit_optin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "allow_console_email_sender", True)
    sender = get_email_sender()
    assert isinstance(sender, _ConsoleEmailSender)


@pytest.mark.unit
async def test_console_sender_logs_link_does_not_raise() -> None:
    sender = _ConsoleEmailSender()
    await sender.send_magic_link(to="a@example.com", link="http://x/exchange?token=abc")


@pytest.mark.unit
async def test_smtp_sender_raises_until_implemented() -> None:
    sender = _SmtpEmailSender()
    with pytest.raises(NotImplementedError):
        await sender.send_magic_link(to="a@example.com", link="http://x")
