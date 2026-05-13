"""JWT signing / verification tests."""

from __future__ import annotations

import time
import uuid

import pytest

from plus_one.config import settings as live_settings
from plus_one.core.auth.jwt import (
    InvalidTokenError,
    create_access_token,
    decode_access_token,
)


@pytest.mark.unit
def test_create_and_decode_roundtrip() -> None:
    user_id = uuid.uuid4()
    token = create_access_token(user_id)
    payload = decode_access_token(token)
    assert payload.user_id == user_id


@pytest.mark.unit
def test_payload_iat_and_exp_make_sense() -> None:
    user_id = uuid.uuid4()
    before = int(time.time())
    payload = decode_access_token(create_access_token(user_id, ttl_minutes=10))
    after = int(time.time())
    assert before <= payload.iat <= after
    delta = payload.exp - payload.iat
    assert 9 * 60 <= delta <= 11 * 60


@pytest.mark.unit
def test_decode_rejects_garbage_token() -> None:
    with pytest.raises(InvalidTokenError):
        decode_access_token("not.a.real.jwt")


@pytest.mark.unit
def test_decode_rejects_token_signed_with_wrong_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = uuid.uuid4()
    good_token = create_access_token(user_id)
    monkeypatch.setattr(live_settings, "jwt_secret", "different-secret-entirely")
    with pytest.raises(InvalidTokenError):
        decode_access_token(good_token)


@pytest.mark.unit
def test_decode_rejects_expired_token() -> None:
    user_id = uuid.uuid4()
    expired = create_access_token(user_id, ttl_minutes=-1)
    with pytest.raises(InvalidTokenError):
        decode_access_token(expired)
