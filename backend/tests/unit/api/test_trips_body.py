"""Unit tests for ``CreateTripBody`` — companion_ids validation.

Covers the new field shipped with Batch 2h frontend PRD §4 option A. The
HTTP-path coverage is in ``tests/integration/test_trip_with_profile.py``
(actual filtering behaviour); these stay model-level so a regression on
the public body shape lands a unit-test fail before the integration
suite spins up Postgres.
"""

from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from plus_one.api.trips import CreateTripBody


@pytest.mark.unit
def test_create_trip_body_defaults_companion_ids_to_empty_list() -> None:
    body = CreateTripBody(destination="Tokyo")
    assert body.companion_ids == []


@pytest.mark.unit
def test_create_trip_body_accepts_companion_ids() -> None:
    a, b = uuid.uuid4(), uuid.uuid4()
    body = CreateTripBody(destination="Tokyo", companion_ids=[a, b])
    assert body.companion_ids == [a, b]


@pytest.mark.unit
def test_create_trip_body_rejects_non_uuid_companion_id() -> None:
    with pytest.raises(ValidationError):
        CreateTripBody(destination="Tokyo", companion_ids=["not-a-uuid"])  # type: ignore[list-item]


@pytest.mark.unit
def test_create_trip_body_rejects_more_than_50_companion_ids() -> None:
    ids = [uuid.uuid4() for _ in range(51)]
    with pytest.raises(ValidationError):
        CreateTripBody(destination="Tokyo", companion_ids=ids)
