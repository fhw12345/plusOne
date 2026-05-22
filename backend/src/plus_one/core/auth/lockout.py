"""Login lockout (batch-2m).

Tracks failed-password attempts per user row. After
:data:`settings.login_max_failed_attempts` failures the account is
locked for :data:`settings.login_lockout_minutes`.

State lives on the User row itself (``failed_login_attempts`` +
``locked_until``) — single source of truth across replicas + survives
process restarts.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from plus_one.config import settings

if TYPE_CHECKING:
    from plus_one.core.db.models import User


def is_locked(user: User) -> bool:
    """True iff ``user.locked_until`` is set and still in the future."""
    if user.locked_until is None:
        return False
    return user.locked_until > datetime.now(UTC)


def record_failed_attempt(user: User) -> bool:
    """Increment ``failed_login_attempts``. Lock on threshold.

    Returns True iff the account just got locked by this attempt.
    """
    user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
    if user.failed_login_attempts >= settings.login_max_failed_attempts:
        user.locked_until = datetime.now(UTC) + timedelta(minutes=settings.login_lockout_minutes)
        user.failed_login_attempts = 0
        return True
    return False


def reset_attempts(user: User) -> None:
    """Clear the counter + lock window on a successful login."""
    user.failed_login_attempts = 0
    user.locked_until = None
