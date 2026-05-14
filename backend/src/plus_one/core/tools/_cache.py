"""Shared cache primitive used by fixture-backed tools.

The first batch of tools doesn't talk to live APIs; they read pre-collected
JSON fixtures from a directory tree. This module gives each tool a
deterministic ``cache_key -> path`` resolver and a load helper that returns
``[]`` for cache misses (rather than raising) so demos degrade gracefully.

Layout:

    fixtures/
    ├── reddit/
    │   └── tokyo_ramen_tonkotsu.json
    ├── xhs/
    │   └── tokyo_ramen_tonkotsu.json
    └── google_places/
        └── tokyo_ramen.json
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger()


def slugify(text: str) -> str:
    """Lowercase, ascii-alphanumeric-and-underscore. Stable for cache keys."""
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", text.lower()).strip("_")
    return cleaned or "empty"


# Cache keys longer than this get hashed so Windows file paths stay sane.
_KEY_LENGTH_LIMIT = 100


def cache_key(*parts: str) -> str:
    """Build a deterministic cache key from components.

    For short, human-friendly keys (≤ ``_KEY_LENGTH_LIMIT`` chars total) we
    slugify and join with ``__``. For longer keys we hash to keep filenames
    sane on Windows.
    """
    pieces = [slugify(p) for p in parts if p]
    joined = "__".join(pieces)
    if len(joined) <= _KEY_LENGTH_LIMIT:
        return joined
    return hashlib.sha256(joined.encode()).hexdigest()[:32]


def load_json_fixture(directory: Path, key: str) -> list[dict[str, Any]]:
    """Load ``directory/<key>.json`` as a list of dicts. Empty list on miss."""
    path = directory / f"{key}.json"
    if not path.exists():
        logger.info("cache_miss", path=str(path))
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        logger.warning("cache_unexpected_shape", path=str(path), got=type(raw).__name__)
        return []
    return raw
