"""Unit tests for ``CreateTripBody`` — companion_ids validation.

Covers the new field shipped with Batch 2h frontend PRD §4 option A. The
HTTP-path coverage is in ``tests/integration/test_trip_with_profile.py``
(actual filtering behaviour); these stay model-level so a regression on
the public body shape lands a unit-test fail before the integration
suite spins up Postgres.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

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


# === Batch-2o: dates + budget =============================================


@pytest.mark.unit
def test_create_trip_body_dates_and_budget_default_to_none() -> None:
    body = CreateTripBody(destination="Tokyo")
    assert body.date_start is None
    assert body.date_end is None
    assert body.budget_amount is None
    assert body.budget_currency is None


@pytest.mark.unit
def test_create_trip_body_accepts_full_payload() -> None:
    start = datetime(2026, 10, 12, tzinfo=UTC)
    end = datetime(2026, 10, 19, tzinfo=UTC)
    body = CreateTripBody(
        destination="Tokyo",
        date_start=start,
        date_end=end,
        budget_amount=2500,
        budget_currency="USD",
    )
    assert body.date_start == start
    assert body.date_end == end
    assert body.budget_amount == 2500
    assert body.budget_currency == "USD"


@pytest.mark.unit
def test_create_trip_body_accepts_equal_start_and_end() -> None:
    ts = datetime(2026, 10, 12, tzinfo=UTC)
    body = CreateTripBody(destination="Tokyo", date_start=ts, date_end=ts)
    assert body.date_start == body.date_end


@pytest.mark.unit
def test_create_trip_body_rejects_end_before_start() -> None:
    start = datetime(2026, 11, 5, tzinfo=UTC)
    end = start - timedelta(days=3)
    with pytest.raises(ValidationError) as exc:
        CreateTripBody(destination="Tokyo", date_start=start, date_end=end)
    assert "date_end must be on or after date_start" in str(exc.value)


@pytest.mark.unit
def test_create_trip_body_accepts_only_start_date() -> None:
    body = CreateTripBody(
        destination="Tokyo", date_start=datetime(2026, 10, 12, tzinfo=UTC)
    )
    assert body.date_start is not None
    assert body.date_end is None


@pytest.mark.unit
def test_create_trip_body_accepts_only_end_date() -> None:
    body = CreateTripBody(
        destination="Tokyo", date_end=datetime(2026, 10, 19, tzinfo=UTC)
    )
    assert body.date_end is not None
    assert body.date_start is None


@pytest.mark.unit
def test_create_trip_body_rejects_negative_budget() -> None:
    with pytest.raises(ValidationError):
        CreateTripBody(destination="Tokyo", budget_amount=-1)


@pytest.mark.unit
def test_create_trip_body_accepts_zero_budget() -> None:
    body = CreateTripBody(destination="Tokyo", budget_amount=0)
    assert body.budget_amount == 0


@pytest.mark.unit
def test_create_trip_body_rejects_budget_over_ceiling() -> None:
    with pytest.raises(ValidationError):
        CreateTripBody(destination="Tokyo", budget_amount=10_000_001)


@pytest.mark.unit
def test_create_trip_body_rejects_non_integer_budget() -> None:
    # pydantic v2 strict-ish int coercion rejects 2.5 (fractional float).
    with pytest.raises(ValidationError):
        CreateTripBody(destination="Tokyo", budget_amount=2.5)  # type: ignore[arg-type]


@pytest.mark.unit
def test_create_trip_body_rejects_unknown_currency() -> None:
    with pytest.raises(ValidationError) as exc:
        CreateTripBody(destination="Tokyo", budget_currency="ZZZ")
    assert "budget_currency must be one of" in str(exc.value)


@pytest.mark.unit
@pytest.mark.parametrize(
    "code", ["USD", "EUR", "JPY", "CNY", "GBP", "TWD", "KRW", "AUD"]
)
def test_create_trip_body_accepts_each_whitelisted_currency(code: str) -> None:
    body = CreateTripBody(destination="Tokyo", budget_currency=code, budget_amount=10)
    assert body.budget_currency == code


@pytest.mark.unit
def test_create_trip_body_rejects_currency_wrong_length() -> None:
    with pytest.raises(ValidationError):
        CreateTripBody(destination="Tokyo", budget_currency="US")
    with pytest.raises(ValidationError):
        CreateTripBody(destination="Tokyo", budget_currency="USDX")
