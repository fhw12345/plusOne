# Plus One — Product Requirements Document

> Locked: 2026-05-13. This is the canonical PRD. Changes require an ADR.

## 1. Tagline

AI travel planner — extracts scattered local experience from Reddit /
Xiaohongshu into structured **"local gems vs tourist traps"** reports,
with Chinese / English dual-source perspectives and information-disagreement
detection.

## 2. Target user

- **Primary**: Chinese-speaking travelers, age 30-45, middle class, OK with English
- **Travel style**: Independent (not package tours), 1-3 trips/year, deep planning 1-3 months ahead
- **Pain points**: Sponsored content overload, single-source bias, no time to read 50 Reddit threads
- **Companion shape**: Often couples or small groups; one person plans for everyone

## 3. Core value proposition

The product makes one promise:
> *"I read what locals actually said in two languages, called out the sponsored stuff,
> and showed you where Chinese and English communities disagree — with receipts."*

Three supporting capabilities (not the headline, but felt by users):
1. Total-cost transparency (entry + transit + meals + tips)
2. Personalized to user + companion preferences
3. Every recommendation is sourced (clickable evidence)

## 4. Scope (MVP)

### Input
- **Mode D — Hybrid**: structured fields (destination / dates / party / budget)
  + free text + 0-3 LLM-generated follow-up questions

### Output
- **Layout**: Top TL;DR → Tabs (🤝 Together / 🚶 You-only / 🚶‍♀️ Partner-only /
  ⚠️ Disagreement / 🌟 Local Gems / ⚠️ Tourist Traps) → Expandable cards
- **Per card**: name, evidence count, per-person match scores, expand for sources
- **Disagreement card**: surfaces where Chinese sources vs English sources diverge

### Perspective + language toggles
- Perspective: [Chinese community] [English community] [**Fused (default)**]
- Output language: [中文] [English]

### Personalization (MVP — Profile schema b)
- Explicit preferences (loves / hates) per user + per companion
- Companion profiles filled by main user (companions don't need accounts)
- `implicit_preferences` field exists in schema but learning algorithm is v2
- Per-card per-person match scores

### Post-report actions (MVP)
- Save report to "My Trips"
- Share via link
- Export Markdown / PDF
- Conversational refinement ("change Day 2 to a different area")

### Data sources (MVP)
- Reddit (PRAW, official API)
- Xiaohongshu (Playwright scrape with 3-tier fallback, see ADR-003)
- Google Places (official API)
- All scraped content cached to DB

### City coverage
- MVP: Tokyo only (most data, biggest demo impact)
- v2: Kyoto, Osaka
- v3: Taipei, Seoul, Bangkok

## 5. Out of scope (explicit)

- Flight search / booking
- Detailed transit (Google Maps does this)
- Photo analysis / upload
- Social features / comments / following
- Direct booking / reservations
- Real-time translation
- Fully autonomous trip booking
- B2B / travel agent version

## 6. Deferred to v2

- Hotel area recommendations (not specific hotels)
- Day-by-day itinerary auto-arrangement (optional)
- Pre-trip monitoring (closures, price changes, seasonal events)
- Real-time weather / events
- Implicit preference learning algorithm
- Companion auto-learning from natural conversation
- Arq + Redis-backed queue (when concurrency demands)

## 7. Deferred to v3

- Post-trip retrospective with ratings
- Cross-trip preference accumulation insights

## 8. Personalization model (Level 4 backend, Profile schema b for MVP)

```yaml
user:
  id: uuid
  email: str
  demographics: {age_range, language}
  travel_style: {budget_sensitivity, pace, comfort}
  explicit_preferences:
    loves: [str]
    hates: [str]
  visited_cities:
    - city: str
      year: int
      rating: int
      feedback: str
  implicit_preferences: []   # MVP: empty; v2: populated by learning

companions:
  - id: uuid
    user_id: uuid              # owner
    name: str
    explicit_preferences: {loves, hates}
    constraints: {dietary, mobility, max_walking}

trips:
  - id: uuid
    user_id: uuid
    destination: str
    dates: {start, end}
    party: {user_id, companion_ids}
    inputs: {budget, free_text, structured}
    reports: [report_id]

feedback:
  - trip_id, card_id, who_for, signal: 'thumb_up'|'thumb_down', text?
```

Privacy: full data export + hard-delete on user request.

## 9. Engineering harness commitments (MVP)

- ruff + mypy strict + pre-commit
- pytest unit + integration; LLM eval suite tracked separately
- GitHub Actions CI (lint + typecheck + test must pass to merge)
- Pydantic validation on all LLM outputs with 3-tier fallback parser
- Prompt versioning (`prompts/{role}/v{N}.md`), prompt change → eval delta required
- Structured logging (structlog JSONL) + Langfuse for LLM traces
- Alembic migrations
- Demo-mode toggle from Day 1 (cached fixtures)
- LLM provider abstraction from Day 1

## 10. Success metrics

### Phase α (development, ~4-6 months)
- F1 ≥ 0.75 on self-built ground-truth set (60 Tokyo places, 2-3 friends do
  independent labeling first; measure inter-annotator agreement before trusting)
- Pairwise LLM-judge win-rate ≥ 60% vs raw GPT-4 baseline (Gemini judges)
- Citation faithfulness ≥ 90% (random 10 claims per report verified against sources)
- 90% of reports complete in < 90s
- Cycle converges in 2-4 rounds on average
- Per-report cost < $1 (token + API)
- Demo-mode 100% offline-runnable
- ≥ 5 friends test, ≥ 75% subjective satisfaction

### Phase β (private beta, 1-2 months)
- 20 real users recruited (e.g. r/JapanTravel)
- Top 10 user-reported issues fixed
- A "what I learned from 20 users" write-up

### Phase γ (public, 1-2 months)
- Public GitHub repo
- Eval methodology blog post published
- "20 users" learnings post published
- Show HN
- 5-min demo video
- ≥ 3 live interview demos

## 11. Project name

**Plus One** — chosen for double meaning ("extra perspective" + "travel companion").
Tagline: "Travel with another perspective."

## 12. Reviewer notes (for context)

A senior PM/eng review (2026-05-13) flagged:
- Schedule risk dominates technical risk
- LLM does 80% of perceived value — defensibility must come from retrieval +
  eval + disagreement detection, not agent plumbing
- XHS scraping is single-point-of-failure for demo (mitigated by demo-mode + fallback)
- Self-labeled ground truth is circular (mitigated by inter-annotator agreement)
- Level-4 personalization with <100 users learns nothing (mitigated by MVP=schema b,
  algorithm deferred to v2)

The decision to keep XHS scraping + custom cycle framework + dynamic profile
schema is intentional and accepts a 6-12 month timeline rather than 10 weeks.
