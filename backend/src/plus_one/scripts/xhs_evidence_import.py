"""Import crawled XHS facts into structured Postgres evidence tables.

This module intentionally stores only facts from crawled notes: posts,
locally cached images, and candidate/query matches. Coverage summaries and
next-crawl queues are derived from these facts and stay outside PG.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from plus_one.config import settings
from plus_one.core.db.models import XHSPost, XHSPostImage, XHSPostMatch
from plus_one.core.db.session import session_scope

if TYPE_CHECKING:
    from pathlib import Path

_XHS_NOTE_ID_RE = re.compile(r"/(?:explore|search_result|discovery/item)/([A-Za-z0-9]+)")
_PG_MAX_BIND_PARAMS = 32767
_POST_INSERT_COLUMNS = 10
_IMAGE_INSERT_COLUMNS = 8
_MATCH_INSERT_COLUMNS = 12
_MIN_RELEVANCE_SCORE = 0.5


@dataclass(slots=True)
class PostRow:
    note_id: str
    canonical_url: str
    title: str
    body: str
    author: str
    likes: int
    comments: int
    raw_payload: dict[str, Any]
    fetched_at: datetime | None


@dataclass(slots=True)
class ImageRow:
    note_id: str
    source_url: str
    local_url: str
    local_path: str
    byte_count: int | None
    content_type: str
    raw_payload: dict[str, Any]


@dataclass(slots=True)
class MatchRow:
    note_id: str
    candidate: str
    destination: str
    category: str
    query: str
    relevance_score: float | None
    matched_terms: list[str]
    quality_version: int | None
    authenticity_score: float | None
    authenticity_reasons: list[str]
    raw_payload: dict[str, Any]


@dataclass(slots=True)
class EvidenceRows:
    posts: list[PostRow] = field(default_factory=list)
    images: list[ImageRow] = field(default_factory=list)
    matches: list[MatchRow] = field(default_factory=list)


@dataclass(slots=True)
class ImportStats:
    posts: int = 0
    images: int = 0
    matches: int = 0


def load_local_cache_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            if not line.strip():
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                rows.append(parsed)
    return rows


def build_evidence_rows(rows: list[dict[str, Any]]) -> EvidenceRows:
    posts_by_note_id: dict[str, PostRow] = {}
    images_by_key: dict[tuple[str, str], ImageRow] = {}
    matches_by_key: dict[tuple[str, str, str], MatchRow] = {}

    for cache_row in rows:
        candidate = _string(cache_row.get("candidate"))
        query = _string(cache_row.get("query"))
        destination = _string(cache_row.get("destination"))
        category = _string(cache_row.get("category"))
        fetched_at = _parse_datetime(cache_row.get("fetched_at"))
        payload = cache_row.get("payload")
        if not candidate or not query or not isinstance(payload, list):
            continue
        for raw_post in payload:
            if not isinstance(raw_post, dict):
                continue
            note_id = _note_id(raw_post)
            if not note_id:
                continue
            post_row = _post_row(note_id, raw_post, fetched_at)
            posts_by_note_id.setdefault(note_id, post_row)
            for image in _image_rows(note_id, raw_post):
                images_by_key.setdefault((image.note_id, image.local_url), image)
            if not _has_quality_checked_match(raw_post, candidate=candidate, query=query):
                continue
            match = _match_row(
                note_id,
                raw_post,
                candidate=candidate,
                destination=destination,
                category=category,
                query=query,
            )
            matches_by_key.setdefault((match.note_id, match.candidate, match.query), match)

    return EvidenceRows(
        posts=list(posts_by_note_id.values()),
        images=list(images_by_key.values()),
        matches=list(matches_by_key.values()),
    )


def _has_quality_checked_match(post: dict[str, Any], *, candidate: str, query: str) -> bool:
    quality_version = _optional_int(post.get("xhs_quality_version"))
    relevance_score = _optional_float(post.get("xhs_relevance_score"))
    matched_terms = _string_list(post.get("xhs_relevance_terms"))
    return (
        quality_version is not None
        and _string(post.get("xhs_candidate")) == candidate
        and _string(post.get("xhs_query")) == query
        and relevance_score is not None
        and relevance_score >= _MIN_RELEVANCE_SCORE
        and bool(matched_terms)
    )


async def import_evidence_rows(evidence: EvidenceRows) -> ImportStats:
    """Upsert evidence rows into PG and return row counts from the input batch."""
    if not evidence.posts:
        return ImportStats()

    async with session_scope() as session:
        now = datetime.now(UTC)
        await _upsert_posts(session, evidence.posts, now)

        post_ids = await _load_post_ids(session, [post.note_id for post in evidence.posts])
        await _upsert_images(session, evidence.images, post_ids, now)
        await _upsert_matches(session, evidence.matches, post_ids, now)

    return ImportStats(posts=len(evidence.posts), images=len(evidence.images), matches=len(evidence.matches))


async def import_local_cache_file(path: Path) -> ImportStats:
    return await import_evidence_rows(build_evidence_rows(load_local_cache_rows(path)))


async def _upsert_posts(session: Any, posts: list[PostRow], now: datetime) -> None:
    for post_batch in _batches(posts, _max_batch_size(_POST_INSERT_COLUMNS)):
        values = [
            {
                "note_id": post.note_id,
                "canonical_url": post.canonical_url,
                "title": post.title,
                "body": post.body,
                "author": post.author,
                "likes": post.likes,
                "comments": post.comments,
                "raw_payload": post.raw_payload,
                "fetched_at": post.fetched_at,
                "updated_at": now,
            }
            for post in post_batch
        ]
        stmt = pg_insert(XHSPost).values(values)
        await session.execute(
            stmt.on_conflict_do_update(
                index_elements=["note_id"],
                set_={
                    "canonical_url": stmt.excluded.canonical_url,
                    "title": stmt.excluded.title,
                    "body": stmt.excluded.body,
                    "author": stmt.excluded.author,
                    "likes": stmt.excluded.likes,
                    "comments": stmt.excluded.comments,
                    "raw_payload": stmt.excluded.raw_payload,
                    "fetched_at": stmt.excluded.fetched_at,
                    "updated_at": now,
                },
            )
        )


async def _load_post_ids(session: Any, note_ids: list[str]) -> dict[str, Any]:
    post_ids: dict[str, Any] = {}
    for note_id_batch in _batches(note_ids, _PG_MAX_BIND_PARAMS):
        result = await session.execute(
            select(XHSPost.note_id, XHSPost.id).where(XHSPost.note_id.in_(note_id_batch))
        )
        post_ids.update(result.all())
    return post_ids


async def _upsert_images(session: Any, images: list[ImageRow], post_ids: dict[str, Any], now: datetime) -> None:
    values = [
        {
            "post_id": post_ids[image.note_id],
            "source_url": image.source_url,
            "local_url": image.local_url,
            "local_path": image.local_path,
            "byte_count": image.byte_count,
            "content_type": image.content_type,
            "raw_payload": image.raw_payload,
            "updated_at": now,
        }
        for image in images
        if image.note_id in post_ids
    ]
    if not values:
        return
    for value_batch in _batches(values, _max_batch_size(_IMAGE_INSERT_COLUMNS)):
        stmt = pg_insert(XHSPostImage).values(value_batch)
        await session.execute(
            stmt.on_conflict_do_update(
                constraint="uq_xhs_post_images_post_local_url",
                set_={
                    "source_url": stmt.excluded.source_url,
                    "local_path": stmt.excluded.local_path,
                    "byte_count": stmt.excluded.byte_count,
                    "content_type": stmt.excluded.content_type,
                    "raw_payload": stmt.excluded.raw_payload,
                    "updated_at": now,
                },
            )
        )


async def _upsert_matches(session: Any, matches: list[MatchRow], post_ids: dict[str, Any], now: datetime) -> None:
    values = [
        {
            "post_id": post_ids[match.note_id],
            "candidate": match.candidate,
            "destination": match.destination,
            "category": match.category,
            "query": match.query,
            "relevance_score": match.relevance_score,
            "matched_terms": match.matched_terms,
            "quality_version": match.quality_version,
            "authenticity_score": match.authenticity_score,
            "authenticity_reasons": match.authenticity_reasons,
            "raw_payload": match.raw_payload,
            "updated_at": now,
        }
        for match in matches
        if match.note_id in post_ids
    ]
    if not values:
        return
    for value_batch in _batches(values, _max_batch_size(_MATCH_INSERT_COLUMNS)):
        stmt = pg_insert(XHSPostMatch).values(value_batch)
        await session.execute(
            stmt.on_conflict_do_update(
                constraint="uq_xhs_post_matches_post_candidate_query",
                set_={
                    "destination": stmt.excluded.destination,
                    "category": stmt.excluded.category,
                    "relevance_score": stmt.excluded.relevance_score,
                    "matched_terms": stmt.excluded.matched_terms,
                    "quality_version": stmt.excluded.quality_version,
                    "authenticity_score": stmt.excluded.authenticity_score,
                    "authenticity_reasons": stmt.excluded.authenticity_reasons,
                    "raw_payload": stmt.excluded.raw_payload,
                    "updated_at": now,
                },
            )
        )


def _max_batch_size(column_count: int) -> int:
    return max(1, min(1000, _PG_MAX_BIND_PARAMS // column_count))


def _batches[T](items: list[T], size: int) -> list[list[T]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


def _post_row(note_id: str, post: dict[str, Any], fetched_at: datetime | None) -> PostRow:
    return PostRow(
        note_id=note_id,
        canonical_url=_canonical_xhs_url(note_id, post),
        title=_string(post.get("title")),
        body=_string(post.get("body")),
        author=_string(post.get("author")),
        likes=_int(post.get("likes")),
        comments=_int(post.get("comments")),
        raw_payload=dict(post),
        fetched_at=fetched_at,
    )


def _image_rows(note_id: str, post: dict[str, Any]) -> list[ImageRow]:
    cached_by_local = {
        _string(item.get("url")): item
        for item in post.get("cached_images") or []
        if isinstance(item, dict) and item.get("url")
    }
    rows: list[ImageRow] = []
    for local_url in _string_list(post.get("images")):
        if not local_url.startswith("/media/"):
            continue
        cached = cached_by_local.get(local_url, {})
        rows.append(
            ImageRow(
                note_id=note_id,
                source_url=_string(cached.get("source_url")),
                local_url=local_url,
                local_path=_local_path(local_url),
                byte_count=_optional_int(cached.get("bytes")),
                content_type=_string(cached.get("content_type")),
                raw_payload=dict(cached) if isinstance(cached, dict) else {},
            )
        )
    return rows


def _match_row(
    note_id: str,
    post: dict[str, Any],
    *,
    candidate: str,
    destination: str,
    category: str,
    query: str,
) -> MatchRow:
    return MatchRow(
        note_id=note_id,
        candidate=candidate,
        destination=destination,
        category=category,
        query=query,
        relevance_score=_optional_float(post.get("xhs_relevance_score")),
        matched_terms=_string_list(post.get("xhs_relevance_terms")),
        quality_version=_optional_int(post.get("xhs_quality_version")),
        authenticity_score=_optional_float(post.get("xhs_authenticity_score")),
        authenticity_reasons=_string_list(post.get("xhs_authenticity_reasons")),
        raw_payload={
            "xhs_relevance_score": post.get("xhs_relevance_score"),
            "xhs_relevance_terms": post.get("xhs_relevance_terms"),
            "xhs_quality_version": post.get("xhs_quality_version"),
            "xhs_authenticity_score": post.get("xhs_authenticity_score"),
            "xhs_authenticity_reasons": post.get("xhs_authenticity_reasons"),
        },
    )


def _note_id(post: dict[str, Any]) -> str:
    raw_id = _string(post.get("id"))
    if raw_id:
        return raw_id
    match = _XHS_NOTE_ID_RE.search(_string(post.get("url")))
    return match.group(1) if match else ""


def _canonical_xhs_url(note_id: str, post: dict[str, Any]) -> str:
    raw = _string(post.get("url"))
    parsed = urlparse(raw)
    if "xiaohongshu.com" not in parsed.netloc:
        return f"https://www.xiaohongshu.com/explore/{note_id}"
    return f"https://www.xiaohongshu.com/explore/{note_id}"


def _local_path(local_url: str) -> str:
    if not local_url.startswith("/media/"):
        return ""
    return str(settings.media_dir / local_url.removeprefix("/media/"))


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _string(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list | tuple):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _int(value: Any) -> int:
    parsed = _optional_int(value)
    return parsed if parsed is not None else 0


def _optional_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return None


def _optional_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    return None
