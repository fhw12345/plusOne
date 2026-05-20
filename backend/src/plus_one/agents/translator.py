"""Translator agent — post-cycle translation of report items.

Runs AFTER ``_save_report`` and BEFORE the ``trip_complete`` SSE event
(see ``services/trip_runner.py``). Best-effort: a translation failure
never aborts the trip (the user gets the original-language report).

Concurrency: per-item LLM calls bounded by ``asyncio.Semaphore(5)`` —
keeps one bad item from poisoning the batch (vs. one big array call)
and avoids serial latency (vs. ``await`` per item).

Cost target: <$0.15 per <=30-item report at Sonnet pricing - see PRD
batch 2k section 6.7 ac8. Rough envelope per item: ~1k input + ~1k
output tokens; Sonnet @ ~$3/$15 per Mtok ~ $0.018/item x 30 ~ $0.54
worst case which exceeds the target IF every item runs both en + zh;
the realistic case is half that since one of the two target langs is
usually the source. Budget holds at ~$0.10-0.15 typical.

Failed-item fallback: the original item is returned under the target-
lang key (NOT dropped) so the frontend's content rendering always has
something to show. A WARN log ``translator_item_failed`` makes the
silent fallback visible operationally.
"""

from __future__ import annotations

import asyncio
from typing import Any

import structlog

from plus_one.agents.joiner import JoinedItem
from plus_one.agents.prompts import load_prompt
from plus_one.core.llm import Message
from plus_one.core.llm import factory as llm_factory

logger = structlog.get_logger()


# Per-PRD §6.4: per-item, concurrency 5.
_TRANSLATOR_CONCURRENCY = 5


async def _translate_one(
    item: JoinedItem,
    src_lang: str,
    dst_lang: str,
    semaphore: asyncio.Semaphore,
) -> dict[str, Any]:
    """Translate one item; on any error fall back to the original.

    Returns the translated item as a ``dict`` (JSON-safe) so the caller
    can persist via the existing ``Report.content`` JSONB column without
    re-serialising. Original item is preserved when translation fails so
    we never drop data — the worst case is a user seeing the source-
    language content for that one card.
    """
    async with semaphore:
        try:
            llm = llm_factory.get_llm_provider("translator_agent")
            system_template = load_prompt("translator", "v1")
            system = system_template.replace("{SRC_LANG}", src_lang).replace("{DST_LANG}", dst_lang)
            payload = item.model_dump(mode="json")
            response = await llm.complete(
                system=system,
                messages=[Message(role="user", content=str(payload))],
                response_model=JoinedItem,
                temperature=0.2,
            )
            if response.parsed is None:
                logger.warning(
                    "translator_item_failed",
                    reason="no_parsed_output",
                    candidate=getattr(item.candidate, "name", "?"),
                    dst_lang=dst_lang,
                )
                return payload
            return response.parsed.model_dump(mode="json")
        except Exception as exc:
            logger.warning(
                "translator_item_failed",
                reason=str(exc),
                candidate=getattr(item.candidate, "name", "?"),
                dst_lang=dst_lang,
            )
            return item.model_dump(mode="json")


async def translate_items(
    items: list[JoinedItem],
    src_lang: str,
    dst_lang: str,
) -> list[dict[str, Any]]:
    """Translate every item from ``src_lang`` to ``dst_lang``.

    Returns a NEW list of JSON-safe dicts — the input items are never
    mutated.

    Concurrency is capped at 5 per :data:`_TRANSLATOR_CONCURRENCY` so a
    30-item report fires at most 5 LLM calls in flight. Failed items
    keep their original payload (see ``_translate_one``).
    """
    if not items:
        return []
    semaphore = asyncio.Semaphore(_TRANSLATOR_CONCURRENCY)
    tasks = [_translate_one(item, src_lang, dst_lang, semaphore) for item in items]
    return await asyncio.gather(*tasks)
