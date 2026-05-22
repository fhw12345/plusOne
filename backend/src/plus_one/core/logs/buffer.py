"""In-memory ring buffer + custom logging handler for the admin log panel.

PRD §7 / §10 / §16. Single shared deque (``maxlen=1000``) holds the most
recent backend log lines AND any frontend console events posted up by
admins. Subscribers (the SSE endpoint) get an asyncio.Queue fed by
:func:`push`.

Secret redaction is performed via :class:`SecretRedactingFilter` —
scrubs SMTP_PASSWORD / JWT_SECRET / password / password_hash / code /
code_hash / access_token / Authorization values.
"""

from __future__ import annotations

import asyncio
import collections
import contextlib
import logging
import re
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel

from plus_one.config import settings

LogSource = Literal["backend", "frontend"]


class LogEntry(BaseModel):
    """One line in the admin log tail."""

    ts: datetime
    level: str
    source: LogSource
    message: str
    logger: str | None = None


_MAX_RING = 1000
_SUB_QUEUE_MAX = 500

_RING: collections.deque[LogEntry] = collections.deque(maxlen=_MAX_RING)
_SUBSCRIBERS: set[asyncio.Queue[LogEntry]] = set()


def snapshot() -> list[LogEntry]:
    """Return the current ring contents (oldest first)."""
    return list(_RING)


def push(entry: LogEntry) -> None:
    """Append + fan out to all live subscribers.

    Per-queue maxsize is 500 — if a subscriber falls behind we drop the
    oldest event for that subscriber rather than block the producer.
    """
    _RING.append(entry)
    for q in list(_SUBSCRIBERS):
        try:
            q.put_nowait(entry)
        except asyncio.QueueFull:
            # Best-effort drop oldest on this subscriber.
            with contextlib.suppress(asyncio.QueueEmpty):
                q.get_nowait()
            with contextlib.suppress(asyncio.QueueFull):
                q.put_nowait(entry)


def subscribe() -> asyncio.Queue[LogEntry]:
    """Register a new subscriber; caller MUST :func:`unsubscribe` later."""
    q: asyncio.Queue[LogEntry] = asyncio.Queue(maxsize=_SUB_QUEUE_MAX)
    _SUBSCRIBERS.add(q)
    return q


def unsubscribe(q: asyncio.Queue[LogEntry]) -> None:
    _SUBSCRIBERS.discard(q)


# === Secret redaction filter =============================================

# Sensitive keys (case-insensitive). Matched in both JSON-ish quoted form
# and "key=value" form.
_SECRET_KEYS = (
    "smtp_password",
    "jwt_secret",
    "password",
    "password_hash",
    "code",
    "code_hash",
    "access_token",
    "authorization",
)


def _build_redact_patterns() -> list[re.Pattern[str]]:
    pats: list[re.Pattern[str]] = []
    for key in _SECRET_KEYS:
        # JSON shape:  "key": "value"
        pats.append(
            re.compile(
                rf'(?i)("?{re.escape(key)}"?\s*[:=]\s*")([^"]*)(")'
            )
        )
        # Bare shape: key=value  (value is non-quoted, non-whitespace,
        # non-comma; stops at delimiter).
        pats.append(
            re.compile(
                rf"(?i)(\b{re.escape(key)}\s*=\s*)([^\s,;'\"]+)"
            )
        )
    return pats


_REDACT_PATTERNS = _build_redact_patterns()
_REPLACEMENT = "***redacted***"


def _redact_runtime_secrets(text: str) -> str:
    """Also nuke any literal occurrence of the configured SMTP password
    or JWT secret value — covers the case where a log line embeds them
    bare (not as ``key=value``)."""
    pw = settings.smtp_password
    if pw and pw in text:
        text = text.replace(pw, _REPLACEMENT)
    js = settings.jwt_secret
    if js and js != "change-me" and js in text:
        text = text.replace(js, _REPLACEMENT)
    return text


def redact(text: str) -> str:
    """Apply key-name + raw-value redaction to ``text``."""
    out = text
    for pat in _REDACT_PATTERNS:
        # The first capture group ends with the opening quote (for JSON
        # shape) or with "key=" (for bare shape). The replacement keeps
        # whatever the third group captured (closing quote) when present.
        if pat.groups == 3:
            out = pat.sub(lambda m: f"{m.group(1)}{_REPLACEMENT}{m.group(3)}", out)
        else:
            out = pat.sub(lambda m: f"{m.group(1)}{_REPLACEMENT}", out)
    return _redact_runtime_secrets(out)


class SecretRedactingFilter(logging.Filter):
    """Logging filter — scrubs secrets from each :class:`LogRecord`."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:
            return True
        record.msg = redact(msg)
        record.args = None
        return True


# === Handler =============================================================


_LEVEL_NAMES = {
    logging.DEBUG: "DEBUG",
    logging.INFO: "INFO",
    logging.WARNING: "WARN",
    logging.ERROR: "ERROR",
    logging.CRITICAL: "CRITICAL",
}


class AdminTailHandler(logging.Handler):
    """Forwards every emitted record into the admin-tail ring buffer."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            raw = record.getMessage()
        except Exception:
            return
        msg = redact(raw)
        ts = datetime.fromtimestamp(record.created, tz=UTC)
        level = _LEVEL_NAMES.get(record.levelno, record.levelname)
        entry = LogEntry(
            ts=ts,
            level=level,
            source="backend",
            message=msg,
            logger=record.name,
        )
        push(entry)


_INSTALLED = False


def install_admin_tail() -> AdminTailHandler:
    """Idempotently install the admin-tail handler on the relevant loggers.

    Returns the installed handler instance — useful for tests that want
    to detach it again.
    """
    global _INSTALLED
    handler = AdminTailHandler(level=logging.DEBUG)
    handler.addFilter(SecretRedactingFilter())

    # Attach to root (catches plus_one.* and anything else) at DEBUG.
    # Attach to uvicorn loggers explicitly so access lines come through
    # at INFO; sqlalchemy.engine clamped to WARNING to keep volume sane.
    targets = (
        ("", logging.DEBUG),
        ("uvicorn", logging.INFO),
        ("uvicorn.access", logging.INFO),
        ("uvicorn.error", logging.INFO),
        ("plus_one", logging.DEBUG),
        ("sqlalchemy.engine", logging.WARNING),
    )
    for name, level in targets:
        lg = logging.getLogger(name)
        # Don't double-install — the handler type is unique to us.
        if not any(isinstance(h, AdminTailHandler) for h in lg.handlers):
            lg.addHandler(handler)
        if lg.level == logging.NOTSET or lg.level > level:
            lg.setLevel(level)

    _INSTALLED = True
    return handler


def clear_for_test() -> None:
    """Test helper — empty the ring + drop subscribers."""
    _RING.clear()
    _SUBSCRIBERS.clear()
