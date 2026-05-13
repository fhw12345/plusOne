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
def test_get_sender_returns_console_in_development(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "app_env", "development")
    sender = get_email_sender()
    assert isinstance(sender, _ConsoleEmailSender)


@pytest.mark.unit
def test_get_sender_returns_smtp_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "app_env", "production")
    sender = get_email_sender()
    assert isinstance(sender, _SmtpEmailSender)


@pytest.mark.unit
async def test_console_sender_logs_link_does_not_raise() -> None:
    sender = _ConsoleEmailSender()
    # Just verify the call completes — log capture is brittle across structlog
    # configurations.
    await sender.send_magic_link(to="a@example.com", link="http://x/exchange?token=abc")


@pytest.mark.unit
async def test_smtp_sender_raises_until_implemented() -> None:
    sender = _SmtpEmailSender()
    with pytest.raises(NotImplementedError):
        await sender.send_magic_link(to="a@example.com", link="http://x")
