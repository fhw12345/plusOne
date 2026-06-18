# Trust-First Beta Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Plus One's beta report experience trust-first by surfacing source health, evidence coverage, dashboard conclusions, public sample report, guided inputs, and card-level feedback.

**Architecture:** Add structured source metadata at the tool-result boundary, aggregate it in the joiner and trip-runner layer, persist additive trust metadata in `reports.content` JSONB, and render reusable trust components across owner, shared, and sample report surfaces. Reuse the existing `feedback` table with a narrow owner-only API. Keep the dashboard derived from report content on the frontend so old reports remain compatible.

**Tech Stack:** FastAPI, SQLAlchemy async, Postgres JSONB, Pydantic, pytest, Next.js App Router, React, TypeScript, Zod, TanStack Query, Vitest, Playwright.

---

## Source Inputs

- Product PRD: `prd.md`
- Report persistence: `backend/src/plus_one/services/trip_runner.py`
- Source fan-out and classification: `backend/src/plus_one/agents/joiner.py`
- Tool envelope: `backend/src/plus_one/core/agents/framework/tools.py`
- Feedback table: `backend/src/plus_one/core/db/models.py`
- Owner report UI: `frontend/components/trips/ReportView.tsx`
- Itinerary report UI: `frontend/components/trips/ItineraryView.tsx`
- Shared report route: `frontend/app/share/[token]/page.tsx`

## Architectural Decisions

1. Store source health and coverage in `reports.content` as optional additive JSON fields. No database migration is required for trust metadata.
2. Extend `ToolResult` with structured `metadata` instead of parsing `notes`. `notes` stays for observability; `metadata` becomes product-safe state.
3. Let tools report their own fetch state, then let `joiner` and `trip_runner` aggregate report-level source health.
4. Derive the dashboard in frontend helper code from `items`, `source_health`, and `coverage_summary`. Avoid persisting duplicated dashboard summaries.
5. Reuse the existing `Feedback` ORM table. The current `signal` column length supports all PRD feedback signals.
6. Preserve trust metadata across refinement reports because `run_refine` does not re-run source tools.
7. Add guided input fields without a trip-table migration by accepting structured fields in create-trip APIs and appending them into the agent-visible query context.
8. Keep shared reports read-only. Shared and sample reports show trust metadata but never feedback controls, private profile data, raw traces, tokens, or admin state.

## System Flow

```mermaid
flowchart LR
    UserInput[Trip form input] --> API[FastAPI trip API]
    API --> Runner[trip_runner]
    Runner --> Joiner[joiner]
    Joiner --> Tools[Reddit / XHS / Foursquare tools]
    Tools --> ToolResult[ToolResult metadata.source_status]
    ToolResult --> Joiner
    Joiner --> RoundHealth[per-round source health]
    RoundHealth --> Runner
    Runner --> ReportContent[reports.content JSONB]
    ReportContent --> OwnerUI[owner report UI]
    ReportContent --> SharedUI[shared report UI]
    SampleFixture[sample-report.json] --> SampleUI[/sample]
    OwnerUI --> FeedbackAPI[owner-only feedback API]
    FeedbackAPI --> FeedbackTable[feedback table]
```

## Target Contracts

### ToolResult Metadata

Add a structured metadata field while preserving existing free-text notes.

```python
class ToolResult[TOut](BaseModel):
    """Wrapped output of a tool call."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    tool: str
    ok: bool = True
    output: TOut | None = None
    error: str | None = None
    notes: str = Field(default="", description="Free-text trace for observability")
    metadata: dict[str, Any] = Field(default_factory=dict)
```

Each source tool returns this product-safe shape when source state is known.

```json
{
  "source_status": {
    "source": "xiaohongshu",
    "status": "cached",
    "evidence_count": 8,
    "note": "XHS evidence came from prewarmed cache."
  }
}
```

### Backend Trust Models

Create `backend/src/plus_one/agents/report_metadata.py` with Pydantic models and aggregation helpers.

```python
SourceName = Literal["reddit", "xiaohongshu", "foursquare"]
SourceStatus = Literal["live", "cached", "partial", "blocked", "fixture", "unavailable"]


class SourceHealth(BaseModel):
    source: SourceName
    status: SourceStatus
    evidence_count: int = Field(default=0, ge=0)
    note: str = Field(default="", max_length=240)


class CoverageSummary(BaseModel):
    total_cards: int = Field(default=0, ge=0)
    cards_with_evidence: int = Field(default=0, ge=0)
    cards_with_multi_source_evidence: int = Field(default=0, ge=0)
    thin_cards: int = Field(default=0, ge=0)
    disagreement_cards: int = Field(default=0, ge=0)
    evidence_by_source: dict[SourceName, int] = Field(default_factory=dict)
    confidence_summary: Literal["strong", "mixed", "thin"] = "thin"
```

### Report Content JSON

`reports.content` remains backward compatible. Old reports can omit every new field.

```json
{
  "items": [],
  "tl_dr": "Strong ramen signal around a few non-obvious picks.",
  "day_plan": [],
  "source_health": {
    "reddit": { "source": "reddit", "status": "blocked", "evidence_count": 0, "note": "Reddit was blocked during this run, so English-community evidence is thin." },
    "xiaohongshu": { "source": "xiaohongshu", "status": "cached", "evidence_count": 12, "note": "XHS evidence came from prewarmed cache." },
    "foursquare": { "source": "foursquare", "status": "live", "evidence_count": 8, "note": "Place metadata was fetched live." }
  },
  "coverage_summary": {
    "total_cards": 10,
    "cards_with_evidence": 8,
    "cards_with_multi_source_evidence": 4,
    "thin_cards": 2,
    "disagreement_cards": 1,
    "evidence_by_source": { "reddit": 3, "xiaohongshu": 12, "foursquare": 8 },
    "confidence_summary": "mixed"
  }
}
```

### Feedback API

```text
POST /api/trips/{trip_id}/feedback
GET  /api/trips/{trip_id}/feedback
```

Signals: `useful`, `not_useful`, `inaccurate`, `too_touristy`, `want_to_go`, `not_interested`.

## File Map

### Backend Changes

| File | Responsibility |
| --- | --- |
| `backend/src/plus_one/core/agents/framework/tools.py` | Add `ToolResult.metadata`. |
| `backend/src/plus_one/core/tools/source_metadata.py` | Build consistent `metadata.source_status` dictionaries. |
| `backend/src/plus_one/core/tools/reddit.py` | Populate source status for cache, live, blocked, empty, and error states. |
| `backend/src/plus_one/core/tools/xiaohongshu.py` | Populate source status for live scrape, cache, public-index partial, fixture, blocked, and degraded states. |
| `backend/src/plus_one/core/tools/foursquare_places.py` | Populate source status for live, cache, fixture fallback, missing key, and empty states. |
| `backend/src/plus_one/agents/report_metadata.py` | Aggregate source health and coverage summaries. |
| `backend/src/plus_one/agents/joiner.py` | Return per-round source health in `JoinerPayload`; add stable `card_id` to `JoinedItem`. |
| `backend/src/plus_one/services/trip_runner.py` | Merge source health, compute coverage, persist trust metadata, and preserve metadata across refine reports. |
| `backend/src/plus_one/api/feedback.py` | Owner-only feedback create and list routes. |
| `backend/src/plus_one/api/trips.py` | Accept guided input fields and pass them into the agent-visible query. |
| `backend/src/plus_one/main.py` | Register feedback router. |
| `backend/src/plus_one/core/db/models.py` | Update feedback comment to the new signal set. |

### Backend Tests

| File | Coverage |
| --- | --- |
| `backend/tests/unit/tools/test_source_metadata.py` | Metadata helper shape and sanitization. |
| `backend/tests/unit/tools/test_tools.py` | ToolResult metadata compatibility. |
| `backend/tests/unit/tools/test_xhs_tiers.py` | XHS live/cache/partial/fixture/degraded status mapping. |
| `backend/tests/unit/agents/test_report_metadata.py` | Source health merge and coverage summary math. |
| `backend/tests/unit/services/test_trip_runner.py` | Report content persists trust metadata. |
| `backend/tests/unit/services/test_trip_runner_refine.py` | Refine reports preserve source health. |
| `backend/tests/unit/api/test_feedback.py` | Feedback validation and ownership. |
| `backend/tests/integration/test_me_export.py` | New feedback signals export. |
| `backend/tests/integration/test_me_delete.py` | Feedback rows are hard-deleted with user data. |

### Frontend Changes

| File | Responsibility |
| --- | --- |
| `frontend/lib/schemas/trips.ts` | Trust metadata schemas, guided input fields, feedback schemas, and `JoinedItemView.card_id`. |
| `frontend/lib/trips/dashboard.ts` | Derive dashboard modules from report content. |
| `frontend/lib/api/trips.ts` | Add feedback API client functions. |
| `frontend/components/trips/SourceHealth.tsx` | Product-safe source status summary. |
| `frontend/components/trips/ReportDashboard.tsx` | Reusable dashboard for owner, shared, and sample reports. |
| `frontend/components/trips/CardFeedback.tsx` | Owner-only card feedback controls. |
| `frontend/components/trips/ReportView.tsx` | Render dashboard and source health before report controls. |
| `frontend/components/trips/ItineraryView.tsx` | Render dashboard and source health before day plan; support read-only mode. |
| `frontend/components/trips/ReportTabs.tsx` | Pass `tripId` and `readonly` into cards. |
| `frontend/components/trips/ItemCard.tsx` | Evidence counts by source, thin-evidence copy, card anchors, and feedback controls. |
| `frontend/components/trips/TripForm.tsx` | Add intent, avoid-list, and trust preference controls. |
| `frontend/app/sample/page.tsx` | Public unauthenticated sample report. |
| `frontend/public/data/sample-report.json` | Stable sample report payload. |
| `frontend/app/page.tsx` | Link to sample report. |
| `frontend/app/share/[token]/page.tsx` | Pass read-only mode into report surfaces. |
| `frontend/lib/report/exportMarkdown.ts` | Include source health and coverage summary in Markdown export. |

## Implementation Tasks

### Task 1: Backend Trust Metadata Foundation

**Files:**
- Create: `backend/src/plus_one/agents/report_metadata.py`
- Create: `backend/tests/unit/agents/test_report_metadata.py`
- Modify: `backend/src/plus_one/agents/joiner.py`

- [ ] **Step 1: Write failing tests for source health and coverage.**

```python
from types import SimpleNamespace

from plus_one.agents.report_metadata import SourceHealth, build_coverage_summary, merge_source_health


def _item(classification="local_gem", confidence=0.8, sources=("reddit",), divergence=0.0):
    return SimpleNamespace(
        classification=classification,
        confidence=confidence,
        evidence=tuple(SimpleNamespace(source=s) for s in sources),
        divergence_score=divergence,
    )


def test_build_coverage_summary_counts_trust_metrics():
    summary = build_coverage_summary([
        _item(sources=("reddit", "xiaohongshu"), confidence=0.86),
        _item(classification="insufficient", confidence=0.2, sources=()),
        _item(sources=("foursquare",), confidence=0.55, divergence=0.8),
    ])

    assert summary.total_cards == 3
    assert summary.cards_with_evidence == 2
    assert summary.cards_with_multi_source_evidence == 1
    assert summary.thin_cards == 1
    assert summary.disagreement_cards == 1
    assert summary.evidence_by_source == {"reddit": 1, "xiaohongshu": 1, "foursquare": 1}
    assert summary.confidence_summary == "mixed"


def test_merge_source_health_marks_degraded_mixed_state_as_partial():
    merged = merge_source_health([
        {"reddit": SourceHealth(source="reddit", status="live", evidence_count=3, note="live")},
        {"reddit": SourceHealth(source="reddit", status="blocked", evidence_count=0, note="blocked")},
    ])

    assert merged["reddit"].status == "partial"
    assert merged["reddit"].evidence_count == 3
```

- [ ] **Step 2: Run the new test and confirm it fails.**

Run: `cd backend && uv run pytest tests/unit/agents/test_report_metadata.py -q`

Expected: import failure for `plus_one.agents.report_metadata`.

- [ ] **Step 3: Implement models and helpers in `report_metadata.py`.**

Core behavior:

```python
SOURCE_ORDER = ("reddit", "xiaohongshu", "foursquare")
STATUS_RANK = {"live": 5, "cached": 4, "partial": 3, "fixture": 2, "blocked": 1, "unavailable": 0}


def merge_source_health(rounds: Sequence[dict[str, SourceHealth]]) -> dict[str, SourceHealth]:
    merged: dict[str, SourceHealth] = {}
    for source in SOURCE_ORDER:
        entries = [row[source] for row in rounds if source in row]
        if not entries:
            merged[source] = SourceHealth(source=source, status="unavailable", evidence_count=0, note=f"{source} did not return usable evidence for this report.")
            continue
        evidence_count = sum(entry.evidence_count for entry in entries)
        statuses = {entry.status for entry in entries}
        status = "partial" if len(statuses) > 1 and ("blocked" in statuses or "unavailable" in statuses) else max(statuses, key=lambda value: STATUS_RANK[value])
        merged[source] = SourceHealth(source=source, status=status, evidence_count=evidence_count, note=_combine_notes([entry.note for entry in entries if entry.note], source, status))
    return merged
```

- [ ] **Step 4: Add `card_id`, `source_health`, and `coverage_summary` to joiner payloads.**

```python
card_id: str = Field(default="", max_length=100)
source_health: dict[str, SourceHealth] = Field(default_factory=dict)
coverage_summary: CoverageSummary | None = None
```

Generate `card_id` deterministically from candidate name plus area, for example `menya-itto-shibuya`. Repair missing IDs in `_repair_item_updates` and `_fallback_items`.

- [ ] **Step 5: Run backend metadata tests.**

Run: `cd backend && uv run pytest tests/unit/agents/test_report_metadata.py -q`

Expected: all tests pass.

### Task 2: Structured Source Metadata In Tools

**Files:**
- Modify: `backend/src/plus_one/core/agents/framework/tools.py`
- Create: `backend/src/plus_one/core/tools/source_metadata.py`
- Modify: `backend/src/plus_one/core/tools/reddit.py`
- Modify: `backend/src/plus_one/core/tools/xiaohongshu.py`
- Modify: `backend/src/plus_one/core/tools/foursquare_places.py`
- Create: `backend/tests/unit/tools/test_source_metadata.py`
- Modify: existing tool tests under `backend/tests/unit/tools/`

- [ ] **Step 1: Write failing metadata helper test.**

```python
from plus_one.core.tools.source_metadata import source_status_metadata


def test_source_status_metadata_shape():
    metadata = source_status_metadata(source="reddit", status="blocked", evidence_count=0, note="Reddit was blocked during this run.")

    assert metadata == {
        "source_status": {
            "source": "reddit",
            "status": "blocked",
            "evidence_count": 0,
            "note": "Reddit was blocked during this run.",
        }
    }
```

- [ ] **Step 2: Run the new test and confirm it fails.**

Run: `cd backend && uv run pytest tests/unit/tools/test_source_metadata.py -q`

Expected: import failure for `source_metadata`.

- [ ] **Step 3: Implement `ToolResult.metadata` and `source_status_metadata`.**

```python
def source_status_metadata(*, source: SourceName, status: SourceStatus, evidence_count: int, note: str) -> dict[str, object]:
    return {
        "source_status": {
            "source": source,
            "status": status,
            "evidence_count": max(0, int(evidence_count)),
            "note": " ".join(note.split())[:240],
        }
    }
```

- [ ] **Step 4: Map tool return paths to source statuses.**

| Tool | Return path | Status |
| --- | --- | --- |
| Reddit | cache hit or cache load | `cached` |
| Reddit | successful JSON fetch with posts | `live` |
| Reddit | network access, 401, 403, or 429 failure | `blocked` |
| Reddit | successful fetch with zero posts | `unavailable` |
| XHS | Playwright live scrape with usable posts | `live` |
| XHS | prewarmed DB or local cache hit | `cached` |
| XHS | public search index with limited body text | `partial` |
| XHS | fixture fallback | `fixture` |
| XHS | login wall, security gate, or access failure with no usable evidence | `blocked` |
| XHS | no evidence after all tiers | `unavailable` |
| Foursquare | cache hit or cache load | `cached` |
| Foursquare | live API fetch with places | `live` |
| Foursquare | missing API key with fixture | `fixture` |
| Foursquare | live error with no fixture | `unavailable` |

- [ ] **Step 5: Extend tool tests to assert metadata.**

For each tool test that already asserts `result.notes`, add assertions for `result.metadata["source_status"]["status"]` and `evidence_count` on at least one live/cache/degraded path.

- [ ] **Step 6: Run selected tool tests.**

Run: `cd backend && uv run pytest tests/unit/tools/test_source_metadata.py tests/unit/tools/test_tools.py tests/unit/tools/test_xhs_tiers.py tests/unit/tools/test_reddit_real.py tests/unit/tools/test_foursquare_places_real.py -q`

Expected: all selected tests pass or live-marked tests remain skipped by existing markers.

### Task 3: Persist Source Health And Coverage

**Files:**
- Modify: `backend/src/plus_one/agents/joiner.py`
- Modify: `backend/src/plus_one/services/trip_runner.py`
- Modify: `backend/tests/unit/services/test_trip_runner.py`
- Modify: `backend/tests/unit/services/test_trip_runner_refine.py`

- [ ] **Step 1: Add aggregation test using fake `ToolResult` metadata.**

```python
from plus_one.agents.report_metadata import build_source_health
from plus_one.core.agents.framework.tools import ToolResult


def test_build_source_health_uses_tool_metadata():
    health = build_source_health([[
        ToolResult(tool="reddit_search", ok=True, output=[], metadata={"source_status": {"source": "reddit", "status": "blocked", "evidence_count": 0, "note": "Reddit blocked."}})
    ]])

    assert health["reddit"].status == "blocked"
```

- [ ] **Step 2: Capture per-round metadata in `run_trip`.**

Add `source_health_rounds: list[dict[str, SourceHealth]] = []` beside `latest_tl_dr`. In `joiner_pump`, append `result.payload.source_health` when present. After `run_cycle`, compute merged health and coverage from final `items`.

- [ ] **Step 3: Persist additive fields in `_save_report`.**

Update `_save_report` to accept `source_health` and `coverage_summary`, then add `content["source_health"]` and `content["coverage_summary"]` only when values are present.

- [ ] **Step 4: Preserve metadata in refine reports.**

When `run_refine` loads the previous report, parse `source_health` from `prev.content`, validate through `SourceHealth.model_validate`, recompute coverage against refined items, and pass both into `_save_refine_report`.

- [ ] **Step 5: Run service tests.**

Run: `cd backend && uv run pytest tests/unit/services/test_trip_runner.py tests/unit/services/test_trip_runner_refine.py -q`

Expected: report content includes optional trust metadata; old report shapes still pass.

### Task 4: Owner-Only Card Feedback API

**Files:**
- Create: `backend/src/plus_one/api/feedback.py`
- Modify: `backend/src/plus_one/main.py`
- Modify: `backend/src/plus_one/core/db/models.py`
- Create: `backend/tests/unit/api/test_feedback.py`
- Modify: `backend/tests/integration/test_me_export.py`
- Modify: `backend/tests/integration/test_me_delete.py`

- [ ] **Step 1: Write feedback API tests.**

```python
async def test_create_feedback_requires_trip_owner(client, trip_factory, auth_headers):
    owner, trip = await trip_factory()
    response = await client.post(
        f"/api/trips/{trip.id}/feedback",
        headers=auth_headers(owner),
        json={"card_id": "menya-itto", "signal": "useful", "text": "This helped."},
    )

    assert response.status_code == 201
    assert response.json()["signal"] == "useful"


async def test_create_feedback_hides_cross_user_trip(client, trip_factory, user_factory, auth_headers):
    owner, trip = await trip_factory()
    other = await user_factory()
    response = await client.post(
        f"/api/trips/{trip.id}/feedback",
        headers=auth_headers(other),
        json={"card_id": "menya-itto", "signal": "useful"},
    )

    assert response.status_code == 404
```

- [ ] **Step 2: Implement request and response models.**

```python
FeedbackSignal = Literal["useful", "not_useful", "inaccurate", "too_touristy", "want_to_go", "not_interested"]


class FeedbackBody(BaseModel):
    card_id: str = Field(min_length=1, max_length=100)
    signal: FeedbackSignal
    for_companion_id: UUID | None = None
    text: str | None = Field(default=None, max_length=500)
```

- [ ] **Step 3: Enforce owner-only writes and reads.**

Load `Trip` by `trip_id` and `user_id == current_user.id`. Return 404 for missing or cross-user trips, matching existing delete/share opacity patterns. Shared viewers never hit this API because `/api/shared/{token}` has no auth context.

- [ ] **Step 4: Register the feedback router.**

```python
from plus_one.api.feedback import router as feedback_router

app.include_router(feedback_router)
```

- [ ] **Step 5: Verify export and delete compatibility.**

`GET /api/me/export` already exports `Feedback`. Add assertions that new signal values round-trip. `DELETE /api/me` already cascades feedback through trip deletion; add one assertion for a `too_touristy` row.

- [ ] **Step 6: Run feedback tests.**

Run: `cd backend && uv run pytest tests/unit/api/test_feedback.py tests/integration/test_me_export.py tests/integration/test_me_delete.py -q`

Expected: all selected tests pass.

### Task 5: Guided Trip Input

**Files:**
- Modify: `backend/src/plus_one/api/trips.py`
- Modify: `frontend/lib/schemas/trips.ts`
- Modify: `frontend/components/trips/TripForm.tsx`
- Modify: `frontend/components/trips/TripForm.test.tsx`
- Modify: `frontend/lib/schemas/trips.test.ts`

- [ ] **Step 1: Add backend guided input fields.**

```python
TripIntent = Literal["food", "cafes", "neighborhoods", "attractions", "nightlife", "shopping", "family", "date_trip"]
AvoidPreference = Literal["queues", "chains", "influencer_spots", "high_budget", "heavy_walking", "tourist_menus"]
TrustPreference = Literal["fused", "zh", "en"]

trip_intents: list[TripIntent] = Field(default_factory=list, max_length=8)
avoid: list[AvoidPreference] = Field(default_factory=list, max_length=8)
trust_preference: TrustPreference = "fused"
```

- [ ] **Step 2: Render guided input into agent query context.**

```python
def _build_agent_query(body: CreateTripBody) -> str:
    parts = [body.destination]
    if body.free_text:
        parts.append(body.free_text)
    structured: list[str] = []
    if body.trip_intents:
        structured.append("interests: " + ", ".join(body.trip_intents))
    if body.avoid:
        structured.append("avoid: " + ", ".join(body.avoid))
    if body.trust_preference != "fused":
        structured.append("trust preference: " + body.trust_preference)
    if structured:
        parts.append("Guided input: " + "; ".join(structured))
    return " | ".join(parts)
```

Use this helper in create, clarify, and skip-clarify paths so deferred trips keep the same context.

- [ ] **Step 3: Add frontend Zod enums and defaults.**

Add `TripIntent`, `AvoidPreference`, and `TrustPreference` schemas. Extend `CreateTripBody` with `trip_intents`, `avoid`, and `trust_preference`, each optional on the wire but normalized by the form.

- [ ] **Step 4: Add form controls.**

Use checkbox groups for trip intents and avoid-list, and a segmented control for trust preference. Destination-only input must still submit successfully.

- [ ] **Step 5: Run guided input tests.**

Run: `cd frontend && pnpm test -- components/trips/TripForm.test.tsx lib/schemas/trips.test.ts`

Expected: destination-only, structured-input, and invalid-date cases pass.

### Task 6: Frontend Trust Schemas And Dashboard Helper

**Files:**
- Modify: `frontend/lib/schemas/trips.ts`
- Create: `frontend/lib/trips/dashboard.ts`
- Create: `frontend/lib/trips/dashboard.test.ts`

- [ ] **Step 1: Add frontend trust schemas.**

```typescript
export const SourceStatus = z.enum(["live", "cached", "partial", "blocked", "fixture", "unavailable"]);
export const SourceHealth = z.object({
  source: z.enum(["reddit", "xiaohongshu", "foursquare"]),
  status: SourceStatus,
  evidence_count: z.number().int().nonnegative().default(0),
  note: z.string().default(""),
});
export const CoverageSummary = z.object({
  total_cards: z.number().int().nonnegative().default(0),
  cards_with_evidence: z.number().int().nonnegative().default(0),
  cards_with_multi_source_evidence: z.number().int().nonnegative().default(0),
  thin_cards: z.number().int().nonnegative().default(0),
  disagreement_cards: z.number().int().nonnegative().default(0),
  evidence_by_source: z.record(z.string(), z.number().int().nonnegative()).default({}),
  confidence_summary: z.enum(["strong", "mixed", "thin"]).default("thin"),
});
```

Add optional `source_health` and `coverage_summary` to `TripContent`, and `card_id?: string` to `JoinedItemView`.

- [ ] **Step 2: Write dashboard derivation tests.**

```typescript
import { describe, expect, it } from "vitest";
import { buildReportDashboard } from "@/lib/trips/dashboard";

describe("buildReportDashboard", () => {
  it("selects go picks, skip picks, disagreement, and confidence", () => {
    const dashboard = buildReportDashboard({
      items: [
        { card_id: "a", candidate: { name: "A" }, classification: "local_gem", confidence: 0.9, evidence: [{ source: "reddit" }] },
        { card_id: "b", candidate: { name: "B" }, classification: "tourist_trap", confidence: 0.8, evidence: [{ source: "xiaohongshu" }] },
        { card_id: "c", candidate: { name: "C" }, classification: "neutral", divergence_score: 0.7, evidence: [] },
      ],
      coverage_summary: { total_cards: 3, cards_with_evidence: 2, cards_with_multi_source_evidence: 0, thin_cards: 1, disagreement_cards: 1, evidence_by_source: { reddit: 1, xiaohongshu: 1 }, confidence_summary: "mixed" },
    });

    expect(dashboard.topGo[0]?.name).toBe("A");
    expect(dashboard.topSkip[0]?.name).toBe("B");
    expect(dashboard.biggestDisagreement?.name).toBe("C");
    expect(dashboard.confidenceSummary).toBe("mixed");
  });
});
```

- [ ] **Step 3: Implement `buildReportDashboard`.**

The helper accepts report content-like input and returns stable empty arrays when content is missing. Sort picks by classification, confidence, evidence count, then original index.

- [ ] **Step 4: Run schema and dashboard tests.**

Run: `cd frontend && pnpm test -- lib/schemas/trips.test.ts lib/trips/dashboard.test.ts`

Expected: all selected tests pass.

### Task 7: Report UI Trust Components And Feedback Controls

**Files:**
- Create: `frontend/components/trips/SourceHealth.tsx`
- Create: `frontend/components/trips/ReportDashboard.tsx`
- Create: `frontend/components/trips/CardFeedback.tsx`
- Modify: `frontend/components/trips/ReportView.tsx`
- Modify: `frontend/components/trips/ItineraryView.tsx`
- Modify: `frontend/components/trips/ReportTabs.tsx`
- Modify: `frontend/components/trips/ItemCard.tsx`
- Modify: `frontend/lib/api/trips.ts`
- Create tests for each new component

- [ ] **Step 1: Add feedback API client functions.**

```typescript
export async function submitTripFeedback(tripId: string, body: SubmitFeedbackBodyT): Promise<FeedbackResponseT> {
  const validBody = SubmitFeedbackBody.parse(body);
  const raw = await apiFetch<unknown>(`/api/trips/${tripId}/feedback`, {
    method: "POST",
    body: JSON.stringify(validBody),
  });
  return FeedbackResponse.parse(raw);
}
```

- [ ] **Step 2: Build `SourceHealth`.**

Render these product labels: `live`, `from cache`, `partial`, `blocked this run`, `sample fallback`, and `not found`. Never render raw exceptions, stack traces, internal fixture names, trace IDs, tokens, or provider diagnostics.

- [ ] **Step 3: Build `ReportDashboard`.**

Render top go picks, top skip picks, biggest disagreement, and evidence coverage. Dashboard item links use `#card-${card_id}` and fall back to an index-based anchor when `card_id` is absent.

- [ ] **Step 4: Wire dashboard into both report surfaces.**

`ReportView` and `ItineraryView` render `SourceHealth` and `ReportDashboard` before perspective and language controls. `ItineraryView` gains `readonly?: boolean`; owner route passes default false, shared route passes true.

- [ ] **Step 5: Add evidence-aware card states.**

`ItemCard` derives evidence counts by source from `view.evidence`. It shows thin evidence when evidence length is zero, classification is `insufficient`, or confidence is below `0.45`. It keeps compact EN/ZH classification badges and adds card anchors.

- [ ] **Step 6: Add owner-only feedback controls.**

`CardFeedback` renders six compact signal buttons and optional free text. It only renders when `tripId` is present and `readonly` is false. It uses a TanStack mutation and shows submitted state per signal.

- [ ] **Step 7: Run UI component tests.**

Run: `cd frontend && pnpm test -- components/trips/SourceHealth.test.tsx components/trips/ReportDashboard.test.tsx components/trips/CardFeedback.test.tsx components/trips/ReportView.test.tsx components/trips/ItineraryView.test.tsx components/trips/ItemCard.test.tsx`

Expected: all selected tests pass.

### Task 8: Public Sample Report

**Files:**
- Create: `frontend/app/sample/page.tsx`
- Create: `frontend/public/data/sample-report.json`
- Modify: `frontend/app/page.tsx`
- Create: `frontend/e2e/sample.spec.ts`

- [ ] **Step 1: Create a static sample fixture.**

The fixture uses `TripDetail` shape with `status: "complete"`, realistic `items`, `source_health`, and `coverage_summary`. Use 5 to 7 hand-curated sample cards. Every strong sample card needs at least one source note. The sample must be static and must not call external services.

- [ ] **Step 2: Implement `/sample`.**

Import the JSON fixture, validate it with `TripDetail.parse`, label the route as a sample, and render `ReportView` or `ItineraryView` with `readonly`.

- [ ] **Step 3: Link from landing page.**

Add a clear unauthenticated path from `frontend/app/page.tsx` to `/sample`.

- [ ] **Step 4: Add Playwright smoke test.**

```typescript
import { expect, test } from "@playwright/test";

test("landing links to public sample report", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("link", { name: /sample/i }).click();
  await expect(page).toHaveURL(/\/sample$/);
  await expect(page.getByText(/source/i).first()).toBeVisible();
});
```

- [ ] **Step 5: Run sample test.**

Run: `cd frontend && pnpm e2e -- e2e/sample.spec.ts --project=chromium`

Expected: Chromium sample route test passes.

### Task 9: Export, Shared Report, And End-To-End Verification

**Files:**
- Modify: `frontend/lib/report/exportMarkdown.ts`
- Modify: `frontend/lib/report/exportMarkdown.test.ts`
- Modify: `frontend/app/share/[token]/page.tsx`
- Modify: `frontend/e2e/share.spec.ts`
- Modify: `frontend/e2e/trip-flow.spec.ts`

- [ ] **Step 1: Include trust metadata in Markdown export.**

Add a `Source coverage` section above card details. Include source statuses, evidence counts, and confidence summary. Do not include feedback, private profile data, raw traces, share tokens, or admin data.

- [ ] **Step 2: Verify shared read-only rendering.**

Shared pages show dashboard, source health, evidence cards, and itinerary. Feedback controls are absent.

- [ ] **Step 3: Verify owner report rendering.**

Trip completion flow shows dashboard before report tabs or itinerary day plan. Feedback controls are visible only for the owner.

- [ ] **Step 4: Run backend verification.**

```bash
cd backend && uv run ruff check .
cd backend && uv run mypy src
cd backend && uv run pytest -m "not live"
```

- [ ] **Step 5: Run frontend verification.**

```bash
cd frontend && pnpm lint
cd frontend && pnpm typecheck
cd frontend && pnpm test
cd frontend && pnpm e2e -- e2e/sample.spec.ts e2e/share.spec.ts e2e/trip-flow.spec.ts --project=chromium
```

Expected: all commands exit 0. Live source tests remain opt-in through the existing `live` marker.

## Acceptance Coverage

| PRD Area | Covered By |
| --- | --- |
| Public sample report | Task 8 |
| Guided trip input | Task 5 |
| Report dashboard | Tasks 6 and 7 |
| Source health summary | Tasks 1, 2, 3, and 7 |
| Evidence-aware cards | Task 7 |
| Chinese, English, fused perspectives | Existing toggles plus Task 7 dashboard disagreement rendering |
| Card-level feedback | Tasks 4 and 7 |
| Shared trustworthy report | Task 9 |
| Export and hard delete | Tasks 4 and 9 |

## Rollout Plan

1. Ship backend metadata and feedback API behind normal report rendering. Old reports still render because every new JSON field is optional.
2. Ship frontend dashboard and source health for owner and shared reports. Empty or old metadata falls back to derived evidence counts and thin-evidence copy.
3. Ship `/sample` after the sample fixture is manually reviewed for safe source snippets and no private data.
4. Use private beta feedback rows to review false positives, touristy misses, evidence gaps, and confusing source-health copy.

## Risks And Mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Tool metadata drifts from notes | Users see incorrect source health | Tests assert metadata on cache, live, blocked, partial, and fixture paths. |
| Multi-iteration reports lose early source state | Coverage undercounts evidence | `trip_runner` merges source-health maps across every joiner round. |
| Refined reports look unsourced | Users lose trust after refinement | `run_refine` preserves previous source health and recomputes coverage over refined items. |
| Dashboard overstates weak evidence | Users over-trust summaries | Thin cards, degraded source copy, and dashboard links to card evidence remain visible. |
| Shared route leaks owner-only affordances | Privacy and trust regression | Shared route passes `readonly`; feedback requires `tripId` and `readonly === false`. |
| Feedback expands into personalization scope | Engineering distraction | API stores feedback only; preference learning stays out of this beta. |
| Sample report implies live personalization | Misleading first impression | Route and fixture label the report as a static sample and make no external calls. |

## Definition Of Done

- Completed reports show source health and coverage summary when new reports are generated.
- Completed owner and shared report pages show dashboard before detailed cards or itinerary.
- At least 80 percent of generated cards show source notes or explicit thin-evidence copy.
- `/sample` renders without authentication and without external services.
- Owner can submit card feedback using all six accepted signals.
- Shared viewers cannot submit feedback.
- Export includes trust metadata and feedback remains included in existing user export.
- Account deletion removes feedback through existing cascade behavior.
- Backend unit and integration tests, frontend unit tests, typecheck, lint, and targeted Playwright tests pass.
