# PRD: Plus One Trust-First Beta

**Author:** Product Management  
**Date:** 2026-06-18  
**Status:** Draft

## 1. Problem Statement

Plus One already has an end-to-end MVP: users can create trips, watch the agent run, receive an itinerary/report, refine it, share it, and export it. The product also has a clear wedge: it reads travel discussions across Reddit and XHS, filters weak or promotional signals, and classifies places as local gems, tourist traps, neutral picks, or thin evidence.

The next product problem is trust. Users should immediately understand why Plus One is better than a generic AI itinerary generator or a listicle. Today, the strongest trust signals exist in the data model and report details, but they are not prominent enough in the user experience. Source degradation is also mostly operational: when Reddit is blocked, XHS is gated, or fixtures are used, users do not get a clear product-level explanation of evidence quality.

The beta should make Plus One feel like an evidence-backed travel research assistant. The first impression must answer: what did Plus One check, how complete was the evidence, where did Chinese-language and English-language communities agree or disagree, and which recommendations are strong enough to act on?

## 2. Product Positioning

### Core Promise

Plus One helps independent travelers find places worth their time by cross-checking Chinese-language and English-language community evidence, calling out hype, and showing receipts.

### Recommended Beta Wedge

Focus on Chinese-speaking independent travelers planning Japan and nearby Asia trips, starting with food, cafes, neighborhoods, and attractions where social-content noise is high.

### What Must Be Felt

- This is not a generic itinerary generator.
- Every strong recommendation has evidence.
- Source gaps are disclosed rather than hidden.
- Chinese-language and English-language signals can be inspected separately.
- The product is especially good at finding when hype and real experience diverge.

## 3. Target Users

### Primary User

Chinese-speaking independent travelers, age 30-45, planning 1-3 trips per year, comfortable reading some English, and willing to spend time avoiding over-marketed places.

### Planning Context

- The user is planning 1-12 weeks before departure.
- The user may travel solo, as a couple, or with a small group.
- The user often has strong dealbreakers: no tourist traps, no long queues, no chains, no over-photographed restaurants, dietary constraints, walking limits, or budget limits.

### Primary Jobs To Be Done

- Help me decide which places are actually worth going to.
- Tell me what Chinese travelers and English-language travelers disagree on.
- Show me the source evidence so I can verify before I commit.
- Help me adapt this plan for the people I am traveling with.

## 4. Goals And Non-Goals

### Goals

- Make evidence quality visible at the top of every completed trip.
- Make source health visible when Reddit, XHS, Foursquare, cache, or fixtures are used.
- Add a concise report dashboard before the itinerary: top go picks, top skip picks, biggest disagreement, and evidence coverage.
- Provide a public sample report that demonstrates product value before sign-up.
- Add card-level feedback so beta learning is tied to specific recommendations.
- Keep the beta focused on evidence-backed travel research, not broad travel booking.
- Preserve the current notebook brand voice while adding clearer trust and provenance cues.

### Non-Goals

- Flight, hotel, restaurant booking, or reservation workflows.
- Real-time transit routing.
- Full worldwide launch positioning.
- A fully autonomous travel agent.
- Social networking, comments, or public user profiles.
- A new scraping strategy for commercial production use.
- Advanced implicit preference learning. Feedback collection is in scope; model learning from feedback is not.

## 5. Success Metrics

### Beta Readiness Metrics

- At least 90% of completed reports show a source health summary.
- At least 90% of completed reports show a report dashboard above detailed cards or itinerary.
- At least 80% of recommendation cards expose at least one source note or clearly state thin evidence.
- Users can identify whether XHS, Reddit, and Foursquare were live, cached, degraded, or missing without opening admin logs.
- A new user can understand product value from the public sample report without creating an account.

### User Outcome Metrics

- 5-10 private beta users complete at least one trip report.
- At least 70% of beta users rate the report as more useful than a generic AI itinerary.
- At least 50% of beta users interact with source notes, perspective toggle, feedback, export, share, or refine.
- Card-level feedback is collected on at least 30 recommendation cards across beta users.

### Quality Metrics

- Citation faithfulness: at least 90% of sampled claims are supported by displayed source notes.
- Degraded-source honesty: no report with fixture-only or source-missing evidence presents itself as fully live-sourced.
- Report completion target: 90% of reports complete in under 90 seconds in the supported beta path, excluding known external source gates.

## 6. User Scenarios

### Scenario 1: Understand The Product Before Sign-Up

**As a** first-time visitor, **I want** to see a real sample report, **so that** I can decide whether Plus One is different from generic travel AI.

**Acceptance Criteria:**

- [ ] Landing page includes a clear path to a sample report.
- [ ] Sample report does not require authentication.
- [ ] Sample report shows the report dashboard, source health, evidence cards, and source notes.
- [ ] Sample report avoids implying live personalization when it is static demo content.

### Scenario 2: Create A High-Quality Trip Request

**As a** planner, **I want** guided inputs for destination, trip style, dislikes, and trust preference, **so that** the report reflects what I actually care about.

**Acceptance Criteria:**

- [ ] Trip form keeps destination, dates, budget, companions, and free text.
- [ ] Trip form adds lightweight prompt scaffolding for desired categories and dealbreakers.
- [ ] User can express anti-preferences such as chains, queues, influencer spots, tourist menus, walking intensity, or budget sensitivity.
- [ ] The form remains usable with destination-only input.

### Scenario 3: Read The Report Dashboard First

**As a** traveler, **I want** the main conclusions before the itinerary, **so that** I can quickly decide what matters.

**Acceptance Criteria:**

- [ ] Completed trip page shows a dashboard before detailed itinerary/cards.
- [ ] Dashboard includes top go picks, top skip picks, biggest disagreement, and source coverage.
- [ ] Dashboard links or scrolls to detailed cards.
- [ ] Dashboard is present for both owner and shared read-only report pages.

### Scenario 4: Inspect Evidence And Source Health

**As a** skeptical planner, **I want** to know what sources were used and whether any source degraded, **so that** I can judge how much to trust the result.

**Acceptance Criteria:**

- [ ] Report top area shows source status for Reddit, XHS, Foursquare, cache, and fixtures when applicable.
- [ ] Each source status uses product language: live, cached, partial, blocked, fixture, or unavailable.
- [ ] Degraded source states are visible to normal users, not only admin users.
- [ ] Cards with thin evidence do not use high-confidence language.

### Scenario 5: Compare Chinese And English Community Perspectives

**As a** user, **I want** to switch between Chinese, English, and fused perspectives, **so that** I can understand community-specific differences.

**Acceptance Criteria:**

- [ ] Existing perspective toggle remains available.
- [ ] Dashboard highlights the largest disagreement if present.
- [ ] Cards show compact EN/ZH classification signals when available.
- [ ] If one side lacks evidence, the UI says that explicitly instead of treating silence as agreement.

### Scenario 6: Give Feedback On Specific Recommendations

**As a** beta user, **I want** to mark a card as useful, wrong, too touristy, or not for me, **so that** future product decisions can use real feedback.

**Acceptance Criteria:**

- [ ] Each card includes lightweight feedback controls.
- [ ] Feedback can be submitted by the report owner only.
- [ ] Feedback supports at least: useful, not useful, inaccurate, too touristy, want to go, not interested.
- [ ] Optional free-text feedback is supported.
- [ ] Feedback is exportable and hard-deletable with user data.

### Scenario 7: Share A Trustworthy Report

**As a** planner, **I want** to share a report with a travel companion, **so that** they can inspect the same evidence and conclusions.

**Acceptance Criteria:**

- [ ] Shared report includes dashboard, source health, evidence cards, and itinerary.
- [ ] Shared report remains read-only.
- [ ] Shared report does not expose private profile, account, admin, token, or raw trace data.
- [ ] Share expiration remains visible.

## 7. Functional Requirements

### 7.1 Report Dashboard

Add a report-level dashboard shown above itinerary and card tabs.

Required modules:

- **Top Go Picks:** 2-3 highest-confidence local gems.
- **Top Skip Picks:** 2-3 strongest tourist-trap or skip signals.
- **Biggest Disagreement:** the card with highest divergence score, if any.
- **Evidence Coverage:** source counts and source health summary.
- **Confidence Summary:** a plain-language note such as strong, mixed, or thin.

### 7.2 Source Health Summary

Expose per-source status at the report level.

Source status values:

- `live`: fetched live during this run.
- `cached`: served from prewarmed DB/local cache.
- `partial`: source returned limited data such as titles, URLs, or images without full body.
- `blocked`: source was gated, rate-limited, or returned access errors.
- `fixture`: fixture fallback was used.
- `unavailable`: source was configured off or no evidence was found.

The system should preserve enough metadata from tools and the trip runner to derive these statuses without scraping logs.

### 7.3 Evidence-Aware Card UI

Cards must make evidence strength visible.

Each card should show:

- Classification and confidence.
- Evidence count by source.
- EN/ZH signal when available.
- A visible thin-evidence state.
- Collapsed source notes with links.
- Promotional or hype warning if detected.

### 7.4 Public Sample Report

Provide one polished sample report as an unauthenticated route.

Requirements:

- Use a stable local fixture or committed sample payload.
- Include realistic source health and evidence notes.
- Do not depend on live external services.
- Link from the landing page.
- Clearly label it as a sample.

### 7.5 Guided Trip Input

Keep the current flexible form, but add optional scaffolding.

Potential fields:

- Trip intent: food, cafes, neighborhoods, attractions, nightlife, shopping, family, date trip.
- Avoid list: queues, chains, influencer spots, high budget, heavy walking, tourist menus.
- Trust preference: Chinese community, English community, fused default.

The backend may initially encode these as structured fields or append them to the trip input context. The UI should not require them.

### 7.6 Card-Level Feedback

Use the existing `feedback` table as the product foundation.

Feedback signals:

- `useful`
- `not_useful`
- `inaccurate`
- `too_touristy`
- `want_to_go`
- `not_interested`

Feedback should include:

- `trip_id`
- `card_id` or stable card identity
- optional `for_companion_id`
- signal
- optional text
- timestamps

### 7.7 Degraded Evidence Copy

The product should explain degraded evidence in user-safe language.

Examples:

- "XHS was available from cache for this report."
- "Reddit was blocked during this run, so English-community evidence is thin."
- "This card has source links, but not enough body text for a strong claim."
- "This recommendation is a maybe, not an anchor."

Avoid exposing raw implementation terms such as stack traces, provider exceptions, or internal fixture file names.

## 8. UX Requirements

### 8.1 Information Hierarchy

Completed trip page order:

1. Trip title and status.
2. Source health and report dashboard.
3. Perspective/language controls.
4. Itinerary or card sections.
5. Source notes and evidence details.
6. Refine, share, export, and history.

### 8.2 Tone

Keep the notebook voice, but pair it with clearer trust language.

Use:

- "source coverage"
- "strong signal"
- "mixed signal"
- "thin evidence"
- "blocked during this run"
- "from cache"

Avoid:

- Overpromising certainty.
- Hiding fallback behavior.
- Calling all outputs recommendations when evidence is weak.

### 8.3 Responsive Behavior

- Dashboard modules stack on mobile.
- Source health remains visible without horizontal scrolling.
- Card feedback controls are compact and do not crowd evidence links.
- Shared reports remain readable without owner-only actions.

## 9. Technical Design

### Architecture

The change spans the backend report payload, frontend report rendering, source-tool metadata, and feedback APIs. The current architecture should remain intact:

- FastAPI backend persists trips/reports in Postgres.
- Agent runner emits reports with JSONB content.
- Frontend renders `TripContent` through `ItineraryView` or `ReportView`.
- Evidence tools already degrade gracefully and log source fallback behavior.
- Existing feedback DB table can be surfaced through API/UI.

### Key Files To Modify

| File | Change |
|------|--------|
| `backend/src/plus_one/agents/joiner.py` | Include report/card evidence metadata needed for dashboard summaries and thin-evidence states. |
| `backend/src/plus_one/services/trip_runner.py` | Persist report-level `source_health` / `coverage_summary` into report content. |
| `backend/src/plus_one/core/tools/xiaohongshu.py` | Return structured source status metadata for live/cache/public-index/fixture/degraded paths. |
| `backend/src/plus_one/core/tools/reddit.py` | Return structured source status metadata for live, blocked, empty, or cached paths. |
| `backend/src/plus_one/core/tools/foursquare_places.py` | Return structured source status metadata for live, missing-key fixture fallback, and empty states. |
| `backend/src/plus_one/api/trips.py` | Expose report content additions and add feedback endpoints if not already present. |
| `backend/src/plus_one/api/shared.py` | Ensure shared reports include safe dashboard/source-health fields. |
| `frontend/lib/schemas/trips.ts` | Add Zod/pass-through view types for `source_health`, `coverage_summary`, dashboard fields, and feedback payloads. |
| `frontend/components/trips/ItineraryView.tsx` | Render dashboard/source health above day plan and update evidence strength UI. |
| `frontend/components/trips/ReportView.tsx` | Render dashboard/source health above report tabs. |
| `frontend/components/trips/ItemCard.tsx` | Add feedback controls, evidence count by source, thin-evidence copy, and hype warnings. |
| `frontend/app/page.tsx` | Add link to public sample report. |
| `frontend/app/share/[token]/page.tsx` | Preserve dashboard/source health in shared read-only view. |
| `frontend/lib/api/trips.ts` | Add feedback API client and sample report client if needed. |

### New Files To Create

| File | Purpose |
|------|---------|
| `frontend/components/trips/ReportDashboard.tsx` | Reusable dashboard for completed owner and shared reports. |
| `frontend/components/trips/SourceHealth.tsx` | Reusable source status summary. |
| `frontend/components/trips/CardFeedback.tsx` | Card-level owner feedback controls. |
| `frontend/app/sample/page.tsx` | Public sample report route. |
| `frontend/public/data/sample-report.json` | Stable sample payload for unauthenticated demo route. |
| `backend/src/plus_one/api/feedback.py` | Feedback API routes if not added inside `trips.py`. |
| `backend/tests/unit/api/test_feedback.py` | API tests for feedback creation/listing/export behavior. |
| `frontend/components/trips/ReportDashboard.test.tsx` | Dashboard rendering tests. |
| `frontend/components/trips/SourceHealth.test.tsx` | Source status rendering tests. |
| `frontend/components/trips/CardFeedback.test.tsx` | Feedback UI behavior tests. |

### Report Content Shape

Report JSONB should support additive fields:

```json
{
  "items": [],
  "tl_dr": "Strong local signal around two ramen stops, with one over-hyped skip and one thin-evidence maybe.",
  "day_plan": [],
  "source_health": {
    "reddit": { "status": "blocked", "evidence_count": 0, "note": "Reddit returned access errors during this run." },
    "xiaohongshu": { "status": "cached", "evidence_count": 12, "note": "XHS evidence came from prewarmed cache." },
    "foursquare": { "status": "live", "evidence_count": 8, "note": "Place metadata was fetched live." }
  },
  "coverage_summary": {
    "total_cards": 10,
    "cards_with_evidence": 10,
    "cards_with_multi_source_evidence": 4,
    "thin_cards": 2,
    "disagreement_cards": 1
  }
}
```

Fields must be additive and optional so old reports still render.

### Feedback API

Suggested endpoints:

```text
POST /api/trips/{trip_id}/feedback
GET  /api/trips/{trip_id}/feedback
```

Suggested request:

```json
{
  "card_id": "menya-itto",
  "signal": "useful",
  "for_companion_id": null,
  "text": "This helped me decide."
}
```

Only the trip owner can create feedback. Shared viewers cannot submit feedback in this beta.

## 10. Dependencies

- No new paid external services.
- No new scraping vendor.
- Existing Postgres feedback table should be reused if compatible.
- Existing XHS prewarm/cache path remains the source of demo stability.
- Existing export and hard-delete flows must include new feedback data.

## 11. Data And Compliance Notes

- Source notes must link back to original sources where URLs exist.
- Do not redistribute scraped content beyond short snippets needed for provenance.
- Public sample report should use safe, stable, non-sensitive sample content.
- Shared reports must not expose account identity, admin metadata, raw traces, tokens, or private companion/profile data.
- Feedback is user data and must be included in export and hard-delete behavior.

## 12. Testing Strategy

### Unit Tests

| Area | Covers |
|------|--------|
| Backend source health builders | Maps tool paths to `live`, `cached`, `partial`, `blocked`, `fixture`, `unavailable`. |
| Backend report persistence | Saves additive source health fields without breaking old report shape. |
| Feedback API | Owner-only creation, validation, listing, export/delete compatibility. |
| Frontend dashboard | Correct top picks, skip picks, disagreement, and coverage display. |
| Frontend source health | Correct rendering for each source status. |
| Frontend card feedback | Submit states, disabled shared state, error states. |

### Integration Tests

| Scenario | Trigger | Expected |
|----------|---------|----------|
| Live/cached mixed report | Create Tokyo ramen trip with cache-first XHS | Dashboard shows cached XHS and available evidence. |
| Reddit blocked | Simulate Reddit 403 | Source health shows Reddit blocked and cards avoid overclaiming English evidence. |
| Fixture fallback | Missing Foursquare key with fixture available | Source health shows fixture/degraded state. |
| Public sample | Visit `/sample` | Sample report renders without auth or external services. |
| Shared report | Open share link | Dashboard/source health render, feedback controls hidden. |
| Feedback | Submit card feedback | Feedback row persists and appears in export. |

### E2E Tests

- Landing to sample report.
- Authenticated trip creation to completed dashboard.
- Perspective toggle with disagreement card.
- Card feedback submission.
- Share link read-only dashboard.

## 13. Rollout Plan

### Phase 1: Internal Alpha Polish

- Add dashboard and source health to existing report pages.
- Add public sample route.
- Add feedback API and UI.
- Validate against existing Tokyo ramen E2E.

### Phase 2: Private Beta

- Recruit 5-10 users.
- Limit positioning to Japan/East Asia planning.
- Encourage food/cafe/neighborhood use cases.
- Review feedback weekly and tag false positives, touristy misses, and evidence gaps.

### Phase 3: Beta Iteration

- Tighten prompt/query generation based on feedback.
- Add more sample reports only after the first sample proves conversion value.
- Consider moving source health into a persistent report audit trail if users rely on it.

## 14. Risks And Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| XHS login wall or security gate | Weak Chinese-community evidence | Prefer prewarmed cache, show source health, keep strict no-fallback tests separate. |
| Reddit 403 | Weak English-community evidence | Show blocked state and avoid fused overconfidence. |
| Dashboard over-simplifies nuanced evidence | Users over-trust summaries | Link dashboard items to cards and show confidence/thin evidence states. |
| Feedback creates scope creep into personalization | Engineering distraction | Collect feedback only; defer learning algorithm. |
| Brand voice hides seriousness | Trust gap | Add plain source/coverage language while keeping notebook tone. |
| Broad city coverage dilutes quality | Weak beta outcomes | Narrow launch wedge to high-signal Japan/East Asia use cases. |

## 15. Open Questions

- [ ] Should source health be generated directly by tools or inferred centrally from tool results and logs?
- [ ] What is the exact stable `card_id` for feedback across refinements and translated reports?
- [ ] Should public sample content be hand-curated, generated from a real cached report, or both?
- [ ] Which beta geography should be named publicly first: Tokyo-only, Japan, or East Asia?
- [ ] Should shared viewers be allowed to leave anonymous feedback in a later beta?

## 16. Product Decision Summary

For the next phase, Plus One should not add broad travel-planning features. It should make the current value legible: evidence, disagreement, source health, and user feedback. The product wins when users believe the report because they can inspect how it was made.
