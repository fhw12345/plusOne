"""Unit tests for the admin-tail buffer, redaction filter, and handler."""

from __future__ import annotations

import logging

import pytest

from plus_one.config import settings
from plus_one.core.logs.buffer import (
    AdminTailHandler,
    SecretRedactingFilter,
    clear_for_test,
    redact,
    snapshot,
)


@pytest.fixture(autouse=True)
def _clear_ring() -> None:
    clear_for_test()


@pytest.mark.unit
def test_redact_scrubs_quoted_json_keys() -> None:
    out = redact('{"password": "hunter2", "code": "123456"}')
    assert "hunter2" not in out
    assert "123456" not in out
    assert out.count("***redacted***") == 2


@pytest.mark.unit
def test_redact_scrubs_bare_key_value() -> None:
    out = redact("authorization=Bearer abc.def.ghi code_hash=$argon2$x")
    assert "Bearer" not in out
    assert "argon2$x" not in out


@pytest.mark.unit
def test_redact_scrubs_jwt_secret_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "jwt_secret", "super-secret-xyz")
    out = redact("the jwt is super-secret-xyz somewhere in the line")
    assert "super-secret-xyz" not in out


@pytest.mark.unit
def test_handler_pushes_to_ring() -> None:
    handler = AdminTailHandler(level=logging.DEBUG)
    handler.addFilter(SecretRedactingFilter())

    logger = logging.getLogger("test.admin.tail.unit")
    logger.handlers.clear()
    logger.propagate = False
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)
    try:
        logger.info("hello backend log")
    finally:
        logger.removeHandler(handler)

    entries = snapshot()
    assert any(e.message == "hello backend log" for e in entries)
    last = [e for e in entries if e.message == "hello backend log"][-1]
    assert last.source == "backend"
    assert last.level == "INFO"


@pytest.mark.unit
def test_handler_redacts_secret_in_log_message() -> None:
    handler = AdminTailHandler(level=logging.DEBUG)
    handler.addFilter(SecretRedactingFilter())

    logger = logging.getLogger("test.admin.tail.redact")
    logger.handlers.clear()
    logger.propagate = False
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)
    try:
        logger.info('user payload: {"password": "should-not-leak"}')
    finally:
        logger.removeHandler(handler)

    msgs = [e.message for e in snapshot()]
    assert any("***redacted***" in m for m in msgs)
    assert not any("should-not-leak" in m for m in msgs)
