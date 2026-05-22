"""Unit tests for argon2id wrappers + email-code generation."""

from __future__ import annotations

import re

import pytest

from plus_one.core.auth.codes import generate_code, hash_code
from plus_one.core.auth.passwords import hash_password, verify_password


@pytest.mark.unit
def test_hash_then_verify_roundtrip() -> None:
    h = hash_password("hunter2pass!")
    assert h.startswith("$argon2id$")
    assert verify_password(h, "hunter2pass!") is True


@pytest.mark.unit
def test_verify_rejects_wrong_password() -> None:
    h = hash_password("hunter2pass!")
    assert verify_password(h, "different") is False


@pytest.mark.unit
def test_verify_rejects_corrupt_hash() -> None:
    assert verify_password("not-a-hash", "hunter2pass!") is False


@pytest.mark.unit
def test_generate_code_is_six_digit_numeric_by_default() -> None:
    code = generate_code()
    assert re.fullmatch(r"\d{6}", code), f"unexpected shape: {code!r}"


@pytest.mark.unit
def test_hash_code_uses_argon2id() -> None:
    h = hash_code("123456")
    assert h.startswith("$argon2id$")
