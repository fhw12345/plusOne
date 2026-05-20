# Batch 2h Backend — Profile + Companions API

**Owner:** Backend
**Branch:** `feat/batch2h-backend-profile-companions` (to be cut from `main`)
**Status:** PRD draft
**Date:** 2026-05-20
**Predecessor:** Batch 2f PR B (`#15` area — trip surface + SSE auth). Schema for `profiles` / `companions` already landed in the initial migration; this batch wires them to HTTP + the agent cycle.

---

## 1. Context

### What already exists (important — scope shrinks accordingly)

PRD §8 (Profile schema b) is already reflected in the ORM and the
initial Alembic migration. The Code Agent must **not** re-create these
tables.

- `backend/src/plus_one/core/db/models.py`
  - `User` — `id`, `email`, `is_active`, `last_login_at`, timestamps. No
    profile columns inline (intentional — profile is a sibling table).
  - `Profile` — `id`, `user_id` (unique FK, cascade), `demographics`,
    `travel_style`, `explicit_preferences`, `visited_cities`,
    `implicit_preferences`, all JSONB, all `nullable=False` with ORM
    `default=dict`/`default=list`. 1:1 with `User` via
    `User.profile` relationship, `cascade="all, delete-orphan"`.
  - `Companion` — `id`, `user_id` (FK, cascade), `name` (`String(100)`),
    `explicit_preferences` JSONB, `constraints` JSONB. Composite unique
    `(user_id, name)` via `uq_companion_user_name`.
  - `trip_companions` association table already wired (Trip↔Companion
    m:n via `lazy="selectin"`).
- `backend/alembic/versions/20260513_0001_initial_schema.py`
  - Creates `profiles`, `companions`, `trip_companions` exactly as the
    PRD §8 calls for.

### What's missing (the scope of this PR)

1. **No HTTP surface** for either resource. The `Profile` row does not
   even get created on signup (`api/auth.py` `request_link` adds only a
   `User` and flushes). Reading `/api/profile` today is a 404.
2. **`AgentContext`** (`core/agents/framework/types.py`) carries only
   `query` / `depth` / `summary` / `scratch` — no user identity, no
   profile, no companions.
3. **`run_trip`** (`services/trip_runner.py:180`) constructs
   `AgentContext(query=query, max_depth=4, phase_timeout=120.0)` with
   no user-derived signal. The query string is just
   `destination | free_text`.
4. **Prompts** in `prompts/producer/v1.md` and `prompts/joiner/v1.md`
   know nothing about user preferences.

### Why now

Frontend Batch 2h needs a real backend to render `/profile` and the
companions manager. Without this PR, "personalization" is a hollow
field on the schema. PRD §3 calls personalization out as supporting
capability #2; PRD §4 "MVP — Profile schema b" lists explicit
loves/hates per user + per companion as in-scope for the MVP. Shipping
this batch unblocks both the frontend manager UI **and** the first
meaningful personalization signal into Producer/Joiner.

### Existing PRD style we match

`docs/prds/batch2f-pr-b-trips.md` — same section order (Context, Goals,
Non-goals, then implementation detail). Same convention of citing
exact file paths + line numbers when relevant.

---

## 2. Goals / Non-goals

### Goals

- **G1** — `GET /api/profile` and `PUT /api/profile` exist, are
  Bearer-authed, and round-trip the four MVP-mutable JSONB fields with
  defaults supplied when the row is missing.
- **G2** — `GET /api/companions` (list), `POST /api/companions`
  (create), `PUT /api/companions/{id}` (update), `DELETE
  /api/companions/{id}` (delete) exist and enforce per-user isolation.
- **G3** — `AgentContext` carries `user_profile` + `selected_companions`
  with backward-compatible defaults (existing tests with the old
  constructor signature keep working).
- **G4** — `run_trip` loads `Profile` + all of the user's `Companion`
  rows from DB and populates `AgentContext` before driving the cycle.
- **G5** — Producer + Joiner inject a "User preferences" + "Companion
  preferences" section into their LLM prompts **only when at least one
  loves/hates entry exists**. Empty profile → no prompt change → all
  existing prompt-snapshot tests stay green.
- **G6** — ruff + mypy strict + pytest all green. Coverage stays ≥ 84%
  (current bar per repo CI).

### Non-goals (explicit)

- **Per-trip companion selection.** PRD §8 includes
  `trips.party.companion_ids`; the frontend "pick which companions are
  on this trip" UI lands separately. For this PR
  `selected_companions == all_user_companions`. The `trip_companions`
  association table stays empty for trips created by this batch — a
  later PR populates it from the frontend selection.
- **Implicit preference learning (v2).** Column exists, API rejects
  attempts to write it.
- **Companion-level `visited_cities`.** PRD §8 doesn't define it for
  companions.
- **Profile photo / avatar.** Out of scope for MVP.
- **Bulk companion import / CSV.** Defer.
- **Data-export / hard-delete privacy endpoint** (PRD §8 "Privacy"
  line). Tracked separately.
- **GIN indexes on JSONB.** We do not query inner JSON fields yet —
  flagged as future-when-needed (§12).
- **Auth or `session_scope` contract changes.** None needed.
- **Any frontend change.** Frontend PR depends on this one.

---

## 3. DB schema — **no schema change**

The DDL already matches the PRD. The Code Agent must verify by reading
`backend/src/plus_one/core/db/models.py` and
`backend/alembic/versions/20260513_0001_initial_schema.py` before
writing anything in this area.

Confirmation checklist (verbatim from the existing model — Code Agent
asserts these in `test_models.py`):

| Table | Column | Type | Nullable | Default |
|---|---|---|---|---|
| `profiles` | `demographics` | JSONB | no | `{}` (ORM `dict`) |
| `profiles` | `travel_style` | JSONB | no | `{}` |
| `profiles` | `explicit_preferences` | JSONB | no | `{}` |
| `profiles` | `visited_cities` | JSONB | no | `[]` (ORM `list`) |
| `profiles` | `implicit_preferences` | JSONB | no | `[]` |
| `companions` | `name` | `String(100)` | no | — |
| `companions` | `explicit_preferences` | JSONB | no | `{}` |
| `companions` | `constraints` | JSONB | no | `{}` |
| `companions` | unique `(user_id, name)` | — | — | `uq_companion_user_name` |

### Why JSONB and not relational sub-tables

Locked decision (matches the existing migration). Recorded here so a
future PR doesn't second-guess it:

1. The shape is well-defined at the Pydantic boundary (`schemas.py`
   added in this PR) so the DB layer doesn't need to enforce shape.
2. We never query *by inner field* in v1 (no "find users who hate
   crowds") — relational normalization would buy nothing for current
   queries.
3. JSONB keeps migrations cheap: adding a field to
   `explicit_preferences` is a Pydantic change, zero DDL.
4. Aggregate fetch of one user's whole profile is a single row.

When (if) we add "find users who love X" queries, add a GIN index on
the relevant JSONB column — flagged in §12.

### Index posture

`companions(user_id)` is already covered by the foreign-key
auto-index in PG plus the composite `uq_companion_user_name`
index. `profiles(user_id)` is unique. No new indexes needed.

---

## 4. Alembic migration — **none**

The PRD originally scoped a migration; research shows the schema
already landed in `20260513_0001_initial_schema.py`. **Do not write a
new migration in this PR.** Adding a no-op upgrade/downgrade pair is
worse than nothing (pollutes history, breaks `downgrade -1` from any
later migration). If the Code Agent finds a missed column or index
during implementation, file it as a separate issue and bring it back
to the team lead — do not silently slip a schema change into this PR.

`alembic upgrade head && alembic downgrade base && alembic upgrade head`
already works for `20260513_0001`; we re-verify in CI as part of §11
acceptance, but no new revision file is required.

---

## 5. API contracts

All endpoints mount under the existing `plus_one.api` package, follow
`api/auth.py` + `api/trips.py` conventions (router with `prefix`,
`tags`, `Annotated` deps, Pydantic body models, explicit `status_code`
+ `response_model`). All require `current_user`
(`backend/src/plus_one/core/auth/deps.py:46-58`). Wire into
`plus_one/main.py` next to `auth_router` and `trips_router`.

### New file: `backend/src/plus_one/api/schemas.py`

Shared request/response Pydantic models (these mirror the JSONB shape
the DB column accepts, but enforce bounds + nested shape):

```python
from pydantic import BaseModel, ConfigDict, Field

class Demographics(BaseModel):
    model_config = ConfigDict(extra="forbid")
    age_range: str | None = Field(default=None, max_length=20)
    language: str | None = Field(default=None, max_length=10)

class TravelStyle(BaseModel):
    model_config = ConfigDict(extra="forbid")
    budget_sensitivity: str | None = Field(default=None, max_length=20)
    pace: str | None = Field(default=None, max_length=20)
    comfort: str | None = Field(default=None, max_length=20)

class ExplicitPreferences(BaseModel):
    model_config = ConfigDict(extra="forbid")
    loves: list[str] = Field(default_factory=list, max_length=50)
    hates: list[str] = Field(default_factory=list, max_length=50)

class VisitedCity(BaseModel):
    model_config = ConfigDict(extra="forbid")
    city: str = Field(min_length=1, max_length=100)
    year: int = Field(ge=1900, le=2100)
    rating: int | None = Field(default=None, ge=1, le=5)
    feedback: str | None = Field(default=None, max_length=500)

class CompanionConstraints(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dietary: list[str] = Field(default_factory=list, max_length=20)
    mobility: str | None = Field(default=None, max_length=50)
    max_walking: int | None = Field(default=None, ge=0, le=100)  # km/day
```

`extra="forbid"` is intentional — rejects unknown keys so a future
field-rename can't silently swallow client typos.

### `GET /api/profile`

```python
class ProfileResponse(BaseModel):
    demographics: Demographics
    travel_style: TravelStyle
    explicit_preferences: ExplicitPreferences
    visited_cities: list[VisitedCity]
```

- `200` — returns the current user's profile. If no `Profile` row
  exists yet, server returns an all-defaults response **without
  creating a row** (lazy create on first `PUT`).
- `401` — unauth (handled by `current_user`).

`implicit_preferences` is omitted from the response body — it's an
internal column not consumer-readable in MVP.

### `PUT /api/profile`

Whole-document semantics. Client sends the full profile object; server
upserts a `Profile` row with the provided values + `implicit_preferences=[]`
(unchanged on existing rows).

```python
class ProfileUpdateBody(BaseModel):
    demographics: Demographics = Field(default_factory=Demographics)
    travel_style: TravelStyle = Field(default_factory=TravelStyle)
    explicit_preferences: ExplicitPreferences = Field(
        default_factory=ExplicitPreferences
    )
    visited_cities: list[VisitedCity] = Field(default_factory=list, max_length=100)
```

- `200` — returns the updated `ProfileResponse`.
- `422` — Pydantic validation (loves/hates > 50, visited_cities > 100,
  unknown key under `Demographics` etc.).
- `401` — unauth.

Note: `PUT` is the only mutator. No `PATCH`. Whole-document keeps the
server stateless about partial updates — the frontend sends what it
read from `GET`, with edits applied.

### `GET /api/companions`

```python
class CompanionResponse(BaseModel):
    id: UUID
    name: str
    explicit_preferences: ExplicitPreferences
    constraints: CompanionConstraints
    created_at: datetime
    updated_at: datetime

class CompanionsListResponse(BaseModel):
    companions: list[CompanionResponse]
```

- `200` — list (ordered by `created_at ASC`). Empty list when the user
  has none. **Hard cap at 20** — once a user has 20 companions, the
  list is returned without paging (we never expect this many).
- `401` — unauth.

### `POST /api/companions`

```python
class CompanionCreateBody(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    explicit_preferences: ExplicitPreferences = Field(
        default_factory=ExplicitPreferences
    )
    constraints: CompanionConstraints = Field(default_factory=CompanionConstraints)
```

- `201` — returns `CompanionResponse` of the created row.
- `409` — name conflict (case-insensitive match against the user's
  existing companions). Detail: `"companion_name_taken"`.
- `409` — at cap (`>= 20` existing companions). Detail:
  `"companion_limit_reached"`. (Server-side defense — frontend hides
  the button.)
- `422` — validation.
- `401` — unauth.

Implementation note on the case-insensitive check: the DB-level unique
constraint is case-*sensitive* (`UNIQUE(user_id, name)`). To honor
case-insensitive uniqueness without adding an index migration, do a
`SELECT ... WHERE user_id = :u AND lower(name) = lower(:n)` pre-check
inside the request transaction. Race window (two concurrent POSTs)
falls through to the DB unique which still 409s the second writer —
acceptable in v1.

### `PUT /api/companions/{id}`

Whole-document update. Body identical to `POST` body shape (without
re-stating `id`).

- `200` — `CompanionResponse`.
- `404` — companion does not exist *or* is not owned by current user.
  Return 404 in both cases — don't leak existence (PRD habit, matches
  `GET /api/trips/{id}` pattern at `api/trips.py:140-141`).
- `409` — rename collides with another of the user's companions.
- `422`, `401` — as above.

### `DELETE /api/companions/{id}`

- `204` — deleted.
- `404` — not found / not owned (same masking as above).
- `401` — unauth.

Cascade: per FK `ondelete="CASCADE"` on `feedback.for_companion_id`
this is `SET NULL`, and `trip_companions` is `CASCADE`. Behavior is
implicit from the existing schema.

### Status-code summary

| Endpoint | OK | Other |
|---|---|---|
| `GET /api/profile` | 200 | 401 |
| `PUT /api/profile` | 200 | 401, 422 |
| `GET /api/companions` | 200 | 401 |
| `POST /api/companions` | 201 | 401, 409, 422 |
| `PUT /api/companions/{id}` | 200 | 401, 404, 409, 422 |
| `DELETE /api/companions/{id}` | 204 | 401, 404 |

---

## 6. AgentContext changes

File: `backend/src/plus_one/core/agents/framework/types.py`.

Add two fields with **backward-compatible defaults** so existing call
sites (`tests/unit/agents/framework/test_types.py`,
`test_cycle.py`, `tests/unit/agents/test_domain_agents.py`,
`services/trip_runner.py:192`) keep working unchanged:

```python
class AgentContext(BaseModel):
    # ...existing fields...

    user_profile: UserProfileForContext = Field(
        default_factory=UserProfileForContext,
        description=(
            "Snapshot of the requesting user's profile at cycle start. "
            "Empty default keeps unit tests that construct AgentContext "
            "without a user (test_cycle.py etc.) working unchanged."
        ),
    )
    selected_companions: list[CompanionForContext] = Field(
        default_factory=list,
        description=(
            "Companions involved in this trip. v1 = all of user's "
            "companions; v2 will be user-selected per trip."
        ),
    )
```

Where the new types are plain `BaseModel`s in the **same file** (not
ORM models — agent code must not import the ORM layer):

```python
class UserProfileForContext(BaseModel):
    model_config = ConfigDict(frozen=True)
    loves: tuple[str, ...] = ()
    hates: tuple[str, ...] = ()
    # NOTE: demographics / travel_style / visited_cities are intentionally
    # omitted in v1 — the agents don't read them yet, and pulling them in
    # would bloat the context for no benefit. Add when an agent needs them.

class CompanionForContext(BaseModel):
    model_config = ConfigDict(frozen=True)
    name: str
    loves: tuple[str, ...] = ()
    hates: tuple[str, ...] = ()
```

`frozen=True` is deliberate — neither phase should mutate this; it's a
read-only signal.

**Read sites** (no `if` gates needed; empty-tuple loves/hates render to
no-op prompt section in §7):

- `agents/producer.py::_build_system_prompt` — extend signature to
  accept `ctx.user_profile` + `ctx.selected_companions` (or just
  read off `ctx` since it's already in scope).
- `agents/joiner.py::joiner` — same, just before the
  `load_prompt("joiner", "v1")` line.

---

## 7. Prompt injection

### Where the text goes

Producer prompt (`prompts/producer/v1.md`) currently has placeholders
`{skills}` and `{prior_summary}`. Add a third placeholder `{preferences}`
**after** `{prior_summary}`. New template tail:

```
## Prior cycle summary

If this is not the first iteration, the Controller's running summary
captures what we've already covered:

{prior_summary}

## User and companion preferences

{preferences}

## Output format
...
```

`_build_system_prompt` formats `{preferences}` from a helper.

Joiner prompt (`prompts/joiner/v1.md`) — append a `## User and
companion preferences` section just before `## Output format`. Joiner
uses `load_prompt("joiner", "v1")` directly, with no `.format`; we
switch it to a tiny `.replace("{preferences}", ...)` (or convert to
`.format` consistently — Code Agent picks). The existing
`prompts/joiner/v1.md` has literal `{...}` JSON braces; if switching to
`.format`, those must be doubled `{{...}}` to match the producer
template style. **Simpler call: use `.replace("{preferences}", body)`
to avoid touching the JSON example braces.** Producer already uses
`.format`, and its JSON example already doubles the braces (lines 30-39
of `producer/v1.md`).

### Helper (lives in a new `agents/preferences.py`)

```python
def render_preferences_section(
    profile: UserProfileForContext,
    companions: list[CompanionForContext],
) -> str:
    lines: list[str] = []
    if profile.loves or profile.hates:
        lines.append("User preferences:")
        if profile.loves:
            lines.append(f"  loves: {', '.join(profile.loves)}")
        if profile.hates:
            lines.append(f"  hates: {', '.join(profile.hates)}")
    relevant_companions = [c for c in companions if c.loves or c.hates]
    if relevant_companions:
        if lines:
            lines.append("")
        lines.append("Companion preferences:")
        for c in relevant_companions:
            parts = []
            if c.loves:
                parts.append(f"loves {', '.join(c.loves)}")
            if c.hates:
                parts.append(f"hates {', '.join(c.hates)}")
            lines.append(f"  {c.name}: {'; '.join(parts)}")
    if not lines:
        return "(none specified)"  # explicit no-op marker; never breaks JSON
    return "\n".join(lines)
```

**Rendered example (with profile)** — what Producer would see verbatim:

```
User preferences:
  loves: ramen, kissaten
  hates: long queues
Companion preferences:
  Anna: loves matcha; hates seafood
```

**Rendered example (empty profile)** — what Producer sees:

```
(none specified)
```

The literal `(none specified)` is the **opt-in graceful** behavior: it
keeps the prompt structure stable (no missing-section diff in eval
baselines) but communicates nothing to the LLM. Existing prompt
snapshot tests that match on the section header stay valid; tests that
match on the *content* of the section will need a one-line update to
expect `(none specified)`. Per §11 verification, run the existing
`tests/unit/agents/test_domain_agents.py` suite first to identify which.

---

## 8. Files to change

| File | Change | Notes |
|---|---|---|
| `backend/src/plus_one/api/schemas.py` | **new** | Pydantic models from §5 |
| `backend/src/plus_one/api/profile.py` | **new** | `GET/PUT /api/profile` router |
| `backend/src/plus_one/api/companions.py` | **new** | full CRUD router |
| `backend/src/plus_one/main.py` | edit | mount the two new routers |
| `backend/src/plus_one/core/agents/framework/types.py` | edit | add `UserProfileForContext`, `CompanionForContext`, two new `AgentContext` fields |
| `backend/src/plus_one/agents/preferences.py` | **new** | `render_preferences_section` helper |
| `backend/src/plus_one/agents/producer.py` | edit | `_build_system_prompt` accepts ctx, passes `{preferences}` to `.format` |
| `backend/src/plus_one/agents/joiner.py` | edit | inject `{preferences}` via `.replace` before `llm.complete` |
| `backend/src/plus_one/prompts/producer/v1.md` | edit | add `## User and companion preferences\n\n{preferences}` block |
| `backend/src/plus_one/prompts/joiner/v1.md` | edit | add the same section with `{preferences}` placeholder before output format |
| `backend/src/plus_one/services/trip_runner.py` | edit | new `_load_profile_context(user_id)` helper; call before `AgentContext(...)`; pass `user_id` into `run_trip` |
| `backend/src/plus_one/api/trips.py` | edit | pass `user.id` to `run_trip(trip_id, query, user_id)` |
| `backend/tests/unit/test_models.py` | **new** | `Profile` defaults, `Companion` unique-per-user |
| `backend/tests/integration/test_profile_api.py` | **new** | §9.b |
| `backend/tests/integration/test_companions_api.py` | **new** | §9.c |
| `backend/tests/unit/agents/test_context_with_profile.py` | **new** | §9.d |
| `backend/tests/integration/test_trip_with_profile.py` | **new** | §9.e |

(No new Alembic file. No migration env changes. No frontend.)

---

## 9. Tests

Follows the existing test layout: `tests/unit/` for pure logic /
single-class, `tests/integration/` for FastAPI + DB end-to-end. Async
test fixtures and the `session_scope`/`get_request_session` overrides
already exist in the conftest used by
`tests/integration/test_trips_sse_auth.py` — reuse them.

### a. `tests/unit/test_models.py` (new)

- `Profile` row written with all-default values reads back as
  `{}`/`[]` for each JSONB column.
- `Companion` `(user_id, name)` unique enforced — `IntegrityError`
  on duplicate.
- Cascade: deleting a `User` deletes its `Profile` + `Companion` rows
  (verifies the `ondelete="CASCADE"` configured in the existing
  migration matches the ORM `cascade="all, delete-orphan"`).

### b. `tests/integration/test_profile_api.py` (new)

- `GET /api/profile` with no row → 200, all-default response, **no row
  created**.
- `PUT /api/profile` with full body → 200, response echoes payload,
  row created.
- `PUT /api/profile` second call → 200, row updated in place (single
  `Profile` row per user maintained by the unique constraint).
- `PUT` with `loves` length 51 → 422.
- `PUT` with `visited_cities` length 101 → 422.
- `PUT` with `demographics.unknown_key=...` → 422 (extra-forbid).
- `PUT` with `implicit_preferences` in body → 422 (extra-forbid on the
  body model).
- No-auth `GET /api/profile` → 401.
- Two-user cross-read: user A `PUT`s, user B `GET`s; user B sees only
  defaults (proves per-user isolation through `current_user`).

### c. `tests/integration/test_companions_api.py` (new)

- Full CRUD happy path: `POST` → 201; `GET` shows it; `PUT` updates;
  `DELETE` 204; subsequent `GET` empty.
- Name uniqueness within a user: second `POST` with same name (any
  case) → 409 `companion_name_taken`.
- Cross-user 404: user B does `GET/PUT/DELETE
  /api/companions/{a_companion_id}` → 404 for all three (does not
  leak existence).
- Cap enforcement: seed 20 companions, 21st `POST` → 409
  `companion_limit_reached`.
- Validation: empty `name` → 422; `name` > 100 chars → 422; unknown key
  in `constraints` → 422.
- No-auth → 401 on all four verbs.

### d. `tests/unit/agents/test_context_with_profile.py` (new)

- Constructing `AgentContext(query="x")` with no profile kwargs →
  `user_profile.loves == ()` etc. (backward compat).
- `render_preferences_section` with empty profile + no companions →
  returns `"(none specified)"`.
- Same with profile loves/hates populated → returns the exact text
  shown in §7.
- Producer prompt includes the section text when profile populated
  (use `_build_system_prompt` directly — pure-function test, no LLM
  call needed).
- Producer prompt with empty profile contains the literal `(none
  specified)` (proves the placeholder is wired but adds no signal).

### e. `tests/integration/test_trip_with_profile.py` (new, light)

- Seed user A with a `Profile` + 1 `Companion`. `POST /api/trips`.
  Monkeypatch `run_cycle` (the framework one used by `trip_runner`) to
  capture the `ctx` it was called with. Assert `ctx.user_profile.loves
  == (...)` and `ctx.selected_companions[0].name == "..."`.
- Pure structural test — does not need real LLM, real tools, or even
  the cycle to converge. Mirrors how
  `tests/integration/test_trips_sse_auth.py` stubs the runner.

### Test data fixtures

Reuse the `User` fixture from
`tests/integration/test_trips_sse_auth.py`. Add a `companion_factory`
helper in the shared conftest if not present (the trips test inserts
trips directly via SQLAlchemy, follow the same approach for
companions).

### Coverage gate

`pytest --cov=plus_one --cov-report=term-missing --cov-fail-under=84`
must pass. New code is roughly 250 LoC; the new tests cover it ≥ 90%
by design.

---

## 10. Migration safety

There is **no migration in this PR**, so the usual "what happens to
existing rows" question reduces to "what does `GET /api/profile`
return for users created before this PR who therefore have no
`profiles` row?"

Answer: §5.`GET /api/profile` is **lazy** — returns all-default
`ProfileResponse` without creating a row. First `PUT` creates the row.
This means:

- Dev DB users from Batch 2f (no profile row) → `GET` returns defaults,
  no surprise 500.
- Backfill not required.
- `users` cascade still works either way — deleting a pre-Batch-2h
  user with no profile row is fine (`profiles.user_id` cascade only
  fires if a row exists).

`alembic upgrade head` + `alembic downgrade -1` on the existing
`20260513_0001` revision continues to round-trip as before — verified
in §11 as a guardrail, not because this PR changes it.

---

## 11. Acceptance criteria

The Ship Agent must verify all of these before opening the PR:

1. **Lint / type:** `ruff check .` clean, `mypy --strict src/plus_one`
   clean (matches repo CI per PRD §9).
2. **Tests:** `pytest backend/tests` all green. Coverage **≥ 84%**.
3. **Schema round-trip (guardrail):** `alembic upgrade head` then
   `alembic downgrade -1` then `alembic upgrade head` against a fresh
   PG container works. (Not strictly necessary since no migration is
   added, but the contract from §10 must keep holding.)
4. **Manual smoke (or curl in PR description):**
   `POST /api/auth/request-link` → exchange → token →
   `PUT /api/profile` → `GET /api/profile` echoes →
   `POST /api/companions` → `GET /api/companions` lists it.
5. **Backward-compat sanity:** all tests in
   `tests/unit/agents/framework/` keep passing **unchanged** (proves
   the `AgentContext` default-factory addition didn't break the
   existing constructor surface).
6. **Prompt-snapshot regression check:** any existing test in
   `tests/unit/agents/test_domain_agents.py` that pins prompt content
   either still passes or is updated to expect the new section with
   `(none specified)` content (no semantic prompt change for empty
   profiles).

---

## 12. Risks

### R1 — JSONB default discipline (low impact, already handled)

The existing migration sets all JSONB columns `nullable=False` but
relies on the ORM `default=dict`/`default=list` to supply the empty
value at INSERT time, with no `server_default`. If a future bare SQL
INSERT happens (workers, manual SQL during ops), it'd error. We are
not adding such an insertion path; flagged for future migrations to
remember.

### R2 — GIN index absence (low, future-when-needed)

We don't query JSONB inner fields in v1. Once "find users who hate X"
appears (probably v2 recommendation analytics), add a GIN index on
`profiles.explicit_preferences` and `companions.explicit_preferences`
in a separate migration. Until then, no index = no risk.

### R3 — Prompt template change & eval baselines

Adding the new section changes the system prompt for Producer + Joiner
even when profile is empty (the literal `(none specified)` text
appears). Plus One has **no eval suite running in CI yet** (PRD §9
mentions eval is tracked separately), so this is a low concrete risk,
but flagged for the team running offline evals that the baseline
snapshot includes the new section. The `(none specified)` design
deliberately keeps the section text constant so an offline diff after
this PR will show one block change rather than per-test churn.

### R4 — Whole-document `PUT` semantics (medium, mitigated by docs)

A frontend that sends a partial body on `PUT /api/profile` will
overwrite the missing fields with defaults. This is per design and
documented in §5; the frontend PR must `GET` then `PUT` (read-modify-
write). Flag in the API docstring + frontend PRD.

### R5 — Case-insensitive uniqueness race

The 409 check on companion name is case-insensitive but the DB-level
UNIQUE constraint is case-sensitive. Two simultaneous
`POST /api/companions {name: "Anna"}` + `{name: "anna"}` would both
pass the pre-check and both INSERT successfully. Acceptable in v1
(single-user-typing-in-a-form usage pattern makes this nearly
impossible). Future fix: add a case-insensitive expression index in a
follow-up migration if it ever bites.

### R6 — `selected_companions = all companions` is a temporary shape

Producer + Joiner today see *every* companion in the user's account.
For a user with 5 companions where only 2 are coming on this trip,
the model gets misleading signal. The frontend PR adds per-trip
selection; until it lands, the prompt will sometimes overweight.
Acceptable tradeoff — the alternative is shipping personalization
behind a frontend that doesn't exist yet.

---

## 13. Ship checklist (for Ship Agent)

- Conventional commit: `feat(batch2h-backend): profile + companions API + prompt prefs`
- PR title same as commit subject; body lists §11 evidence (`pytest`
  summary, `ruff`/`mypy` clean, sample curl).
- Reviewers: backend owners; no frontend reviewer needed.
- Link this PRD in the PR body.
