"""Idempotent admin user seed (batch-2m).

Called from the FastAPI lifespan on startup. If no user with the
configured ``ADMIN_EMAIL`` exists, inserts one with:

  * ``username = ADMIN_USERNAME``
  * ``email = ADMIN_EMAIL``
  * ``password_hash = Argon2id(ADMIN_PASSWORD)``
  * ``is_admin = True``
  * ``email_verified_at = now()``

If the user already exists this is a no-op — we do NOT reset the
password. Operators who need to rotate must do it explicitly.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import select

from plus_one.config import settings
from plus_one.core.auth.passwords import hash_password
from plus_one.core.db.models import User
from plus_one.core.db.session import session_scope

logger = logging.getLogger(__name__)


async def ensure_admin_user() -> None:
    """Create the seeded admin row if missing. Idempotent across restarts."""
    email = settings.admin_email.strip().lower()
    username = settings.admin_username.strip().lower()
    if not email or not username:
        logger.info("admin_seed_skipped: admin_email/admin_username not set")
        return

    async with session_scope() as session:
        result = await session.execute(select(User).where(User.email == email))
        existing = result.scalar_one_or_none()
        if existing is not None:
            logger.info("admin user already present")
            return

        user = User(
            email=email,
            username=username,
            password_hash=hash_password(settings.admin_password),
            is_admin=True,
            is_active=True,
            email_verified_at=datetime.now(UTC),
        )
        session.add(user)
        # session_scope() commits on clean exit.

    logger.info("admin user ensured")
