"""Unit test for the SSE access-token scrubber installed on ``uvicorn.access``."""

from __future__ import annotations

import logging

import pytest

from plus_one.main import _install_access_log_scrubber, _ScrubAccessTokenFilter


def _make_record(msg: str, args: tuple[object, ...] = ()) -> logging.LogRecord:
    return logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname=__file__,
        lineno=0,
        msg=msg,
        args=args,
        exc_info=None,
    )


@pytest.mark.unit
def test_filter_redacts_access_token_in_msg() -> None:
    record = _make_record(
        '127.0.0.1:50000 - "GET /api/trips/abc/stream?access_token=eyJ.foo.bar HTTP/1.1" 200'
    )
    f = _ScrubAccessTokenFilter()
    assert f.filter(record) is True
    assert "access_token=REDACTED" in record.msg
    assert "eyJ.foo.bar" not in record.msg


@pytest.mark.unit
def test_filter_redacts_access_token_inside_args() -> None:
    # uvicorn's access formatter passes the request line as a printf arg, not
    # inlined into msg. Cover that shape too.
    record = _make_record(
        '%s - "%s" %s',
        (
            "127.0.0.1:50000",
            "GET /api/trips/abc/stream?access_token=eyJ.foo.bar&x=1 HTTP/1.1",
            "200",
        ),
    )
    f = _ScrubAccessTokenFilter()
    assert f.filter(record) is True
    assert record.args is not None
    rendered = record.getMessage()
    assert "access_token=REDACTED" in rendered
    assert "eyJ.foo.bar" not in rendered
    # Adjacent query params must survive.
    assert "x=1" in rendered


@pytest.mark.unit
def test_filter_leaves_unrelated_records_unchanged() -> None:
    msg = '127.0.0.1:50000 - "GET /api/trips?foo=bar HTTP/1.1" 200'
    record = _make_record(msg)
    f = _ScrubAccessTokenFilter()
    assert f.filter(record) is True
    assert record.msg == msg


@pytest.mark.unit
def test_install_is_idempotent() -> None:
    access_logger = logging.getLogger("uvicorn.access")
    # main.py already called _install_access_log_scrubber() at import time;
    # calling again must not stack up duplicate filters.
    before = sum(isinstance(f, _ScrubAccessTokenFilter) for f in access_logger.filters)
    _install_access_log_scrubber()
    _install_access_log_scrubber()
    after = sum(isinstance(f, _ScrubAccessTokenFilter) for f in access_logger.filters)
    assert after == before
    assert after >= 1
