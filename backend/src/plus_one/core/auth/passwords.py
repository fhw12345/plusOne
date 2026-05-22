"""Argon2id password hashing.

Wraps ``argon2-cffi``'s :class:`PasswordHasher` with the parameters
called out in PRD §10:

  time_cost   = 3
  memory_cost = 65536 KiB
  parallelism = 4
  hash_len    = 32
  salt_len    = 16

PHC string format is used (the library default). Never serialise hashes
yourself — let argon2 emit / parse the standard ``$argon2id$...`` string.
"""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

# Module-level singleton — PasswordHasher is documented thread-safe and
# stateless apart from its parameters. Reusing it avoids per-call
# parameter validation overhead.
_HASHER = PasswordHasher(
    time_cost=3,
    memory_cost=65536,
    parallelism=4,
    hash_len=32,
    salt_len=16,
)


def hash_password(password: str) -> str:
    """Return a PHC-encoded Argon2id hash of ``password``."""
    return _HASHER.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    """Constant-time verify. Returns False on any mismatch; never raises.

    Wraps the library's :class:`VerifyMismatchError`-throwing API in a
    bool so call sites stay simple. Other argon2 errors (corrupt hash,
    etc.) also surface as False — the caller treats them as auth failure.
    """
    try:
        return _HASHER.verify(password_hash, password)
    except VerifyMismatchError:
        return False
    except Exception:  # pragma: no cover - defensive against corrupt hashes
        return False
