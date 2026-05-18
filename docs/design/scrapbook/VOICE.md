# Plus One — Scrapbook Voice (Direction D)

The single source of truth for what the product *says* to the user.
Lives next to `scrapbook.css` because in Direction D, **copy is the
design surface** — get this wrong and the page reads as another AI
tool no matter how good the CSS is.

> Constraint reminder (from DIRECTION_OPTIONS Part 4): the agent is
> hidden. Never `producer` / `joiner` / `controller`. Never `running` /
> `complete` / `aborted`. Never "depth 2/4". The progress feed speaks
> in *informal first-person, lowercase, present-progressive*, as a
> friend texting while doing the work.

---

## Voice register cheat-sheet

| Trait | Yes | No |
|-------|-----|-----|
| Person | first-person ("i", "i'm", "let me") | "the system", "we", "the agent" |
| Case | lowercase always — except proper nouns | sentence case, ALL CAPS |
| Tense | present-progressive ("checking", "going one more round") | future ("will check"), past ("checked") |
| Length | one short sentence; trail off if helpful | clauses with commas and "furthermore" |
| Tone | curious, mildly informal, *slightly* bemused | enthusiastic, salesy, apologetic |
| Specificity | name the source, the place, the count | vague hedges ("some sources") |
| Asides | one in red-marker `annot` per ~3 lines | every line annotated |
| Emoji | none in core copy. `★`, `→`, `…` only as annotation glyphs | 🎉 🍜 ✨ |
| Hedge | "takes a sec", "interesting", "doing one more pass" | "I think", "maybe", "possibly" |

---

## SSE event → voice copy (full corpus)

Plus One's SSE stream emits these 8 event names (see PRD + Batch 2e).
Every one needs a human-voice line. Many events fire multiple times in
a cycle — provide a small *pool* per event and round-robin so the user
never sees the same sentence twice in one session.

The annotation column is *optional* — used only sometimes, in
red-marker (`.annot`), tilted -1° to -2°.

### `started`
Fires once at cycle kickoff.

| Line pool | Annotation? |
|-----------|-------------|
| `setting up. coffee in hand.` | — |
| `okay, starting on {destination}.` | — |
| `let me see what's out there for {destination}.` | — |

### `iteration_start`
Fires at the top of each pass through producer→joiner→controller.
Reads like *"another lap"* — the user sees us going deeper.

| Iteration # | Line pool |
|-------------|-----------|
| 1 (first loop) | `asking around on reddit. people are loud here, takes a sec to find the quiet ones.` |
| 2 | `going one more round — there's a name that keeps coming up i want to verify.` |
| 3 | `okay, deeper pass. checking the ones with mixed signal.` |
| 4 (depth cap warning) | `last pass — pulling the loose threads together.` |

### `producer`
A fresh batch of candidates just arrived from a source. Always names
the *source* by its everyday name — `reddit`, `小红书`, `google
places` — never the internal tool name (`reddit_search_tool`).

| Source | Line pool | Possible annotation |
|--------|-----------|---------------------|
| reddit | `pulled {n} from r/{subreddit}. reading through.` | `mostly from the last 6 months ★` |
| reddit | `12 names so far from reddit. saving the ones that show up twice.` | — |
| xhs    | `now checking 小红书 for the same names. cross-referencing.` | — |
| xhs    | `xhs has {n} mentions of {place}. people there are quieter, more useful.` | `不是本地人会去 ←` |
| places | `confirming addresses + hours with google places.` | — |

### `joiner`
Cross-validation between sources just produced N confirmed matches.

| Outcome | Line pool |
|---------|-----------|
| n in > n out, healthy | `some of these come up twice — saving the doubles. {n_out} confirmed.` |
| strong agreement on one | `{place} appears in {k} different threads. that's a strong yes.` |
| disagreement found | `two of them disagree about {place}. interesting — going one more round to figure out which side is right.` |
| weak signal | `only {n_out} survived the cross-check. the rest were one-off mentions.` |

### `controller`
The decision moment — *what to do next*. Translate the controller's
reasoning into casual ("i think we need…").

| Decision | Line pool |
|----------|-----------|
| continue, dig further | `i want to know more about {place} before i call it. another pass.` |
| continue, fill a gap | `not enough quiet picks yet — let me look one more time.` |
| stop, satisfied | `tying it all together now.` |
| stop, depth cap | `that's about as far as i should push it — composing what i have.` |

### `cycle_complete`
Fires once at the end, before `trip_complete`.

| Line pool |
|-----------|
| `done. let me lay it out for you.` |
| `okay, that's everything. writing it up.` |

### `trip_complete`
Terminal — pivot the UI to the assembled report. Briefly held in the
scratchpad as a sticky note.

| Line pool (rendered on the yellow sticky-note element) |
|--------|
| `done — pinned at the top.` |
| `all in. check the cards on the left.` |

### `cycle_aborted`
The agent hit a wall. **Critical** for D — this is where most products
revert to *"An error occurred."* and the friend-voice dies. Stay in
voice.

| Reason (from `data.reason`) | Line pool |
|----------------------------|-----------|
| Maestro / LLM unavailable | `hit a wall — couldn't get through to my notes app. give me a sec and try again?` |
| empty producer (no candidates) | `couldn't find anything good for {destination}. either too quiet a corner, or i need a different angle. want to try again with more detail?` |
| validation failure | `something looked off in what i pulled — not going to write it up half-baked. one more try?` |
| unknown / fallback | `something snapped mid-thought. not your fault. try again?` |

Sticky-note style on the scratchpad, red border, `.msg.is-snag` class.

### Heartbeat / waiting (no event, frontend-only)
Between events, after ~3s of silence, show a low-key waiting line so
the user doesn't think the page died:

| Line pool |
|-----------|
| `still reading…` |
| `…hang on, this thread is dense.` |
| `give me a moment.` |

---

## Auth + onboarding copy

### Login (`/login` → `pages/login.html`)
| Slot | Copy |
|------|------|
| Page title (crest) | `PLUS · ONE · say hello` |
| Headline | `let me in` (hand-xxl) |
| Sub | `i'll send you a link.` (.scrawl) |
| Email label | `your email` (.type) |
| Email placeholder | `friend@somewhere.com` |
| Submit button | `send the link` |
| Microcopy after submit | `check your inbox. the link will look like a sticky note.` |
| Error (rate-limited) | `slow down — i already sent one. give it a minute?` |
| Error (server) | `couldn't send it just now. try once more?` |

### Auth-exchange (`/auth/exchange` → `pages/auth-exchange.html`)
| Slot | Copy |
|------|------|
| Crest | `PLUS · ONE · letting you in` |
| Headline | `unpacking the link…` (hand-xxl) |
| Sub (success) | `welcome back. pinning your notes…` (.scrawl, fades to /) |
| Sub (expired) | `this link's gone stale — let me send a fresh one.` |
| Sub (bad token) | `this link doesn't look right. start over?` |

### Profile (`/profile` → `pages/profile.html`)
| Slot | Copy |
|------|------|
| Crest | `PLUS · ONE · about you` |
| Headline | `about you` (hand-xxl) |
| Sub | `the kind of trip you want, in your own words.` |
| Fields | `you go by` / `how you eat` / `how you walk` / `quiet or loud` / `dealbreakers` |
| Save button | `pin it` |
| Saved confirmation | `pinned ★` (annot, fades) |

### Companions (`/companions` → `pages/companions.html`)
| Slot | Copy |
|------|------|
| Crest | `PLUS · ONE · who you bring` |
| Headline | `who you bring` (hand-xxl) |
| Sub | `notes on each person. so i can plan around them too.` |
| Add button | `add someone` |
| Empty state | `nobody added yet. it's okay — solo trips are great too.` |
| Per-card title | name (hand) |
| Per-card body | `they like…` / `they avoid…` (.scrawl) |
| Remove | `take this one out` (link-hand) |

---

## Trip flow copy

### Trip-new (`/trips/new` → `pages/trip-new.html`)
| Slot | Copy |
|------|------|
| Crest | `PLUS · ONE · new reading` |
| Headline | `where are you headed?` (hand-xxl) |
| Sub | `tell me where & what you're hoping for. i'll go look.` |
| Destination label | `the place` |
| Destination placeholder | `e.g. tokyo · kyoto · taipei` |
| Companions | a row of chips toggled on/off |
| Free-text label | `the mood, the foods, what to avoid` |
| Free-text placeholder | `tonkotsu ramen. quiet counters. nothing instagrammy.` |
| Submit button | `go look` |
| Microcopy under submit | `i'll start scribbling as soon as you press it. takes about 90 seconds.` |

### Trip-detail (`/trips/[id]` → `pages/trip-detail.html`)
Existing draft is a great starting point; productionize against the
shared CSS. Crest format mid-cycle:

| Slot | Copy |
|------|------|
| Crest mid-cycle | `PLUS · ONE · reading no. {n} · in progress` |
| Crest done | `PLUS · ONE · reading no. {n} · pinned {date}` |
| Scratchpad header | `what i'm doing — live` |
| Scratchpad header (done) | `what i did — saved` |

### Trip-history (`/` after login → `pages/index.html` & `pages/trip-history.html`)
| Slot | Copy |
|------|------|
| Crest | `PLUS · ONE · your readings` |
| Headline | `your readings` (hand-xxl) |
| Sub | `every place i've looked into for you.` |
| Empty state | `no readings yet. let's make the first one.` (CTA button: `start one`) |
| Per-card body | name of destination + companions chip row + scrawl summary + date stamp |

---

## Status taxonomy (what we *do* show, since we don't show pills)

| Old name | What the page shows instead |
|----------|----------------------------|
| `pending` | nothing yet — the trip card appears with `arriving by next post…` in its stamp slot |
| `running` | live red dot in the scratchpad header + pulsing "what i'm doing — live" |
| `complete` | `pinned {date}` stamp + scratchpad pivots to "what i did — saved" |
| `aborted` | red ticket pinned at top: `hit a wall — couldn't…` + retry link |

That's the whole status system. No badges anywhere.

---

## Place-card verdicts

These are the only canned verdict strings allowed. The agent writes the
explanation; the corner verdict is one of these phrases (hand-written
red `.verdict`):

| Class of place | Allowed verdict strings |
|----------------|-----|
| local gem (high consensus) | `YES. go.` · `this one ★` · `worth the walk.` |
| together (good for group) | `bring everyone.` · `you'll all like this.` |
| solo / specific | `for {name}.` (e.g. `for yuna.`) |
| tourist trap | `skip.` · `not worth it.` · `try {alt} instead →` |
| contested | `two sides — read it.` (only this string, on tickets) |

---

## Out-of-band & system

| Slot | Copy |
|------|------|
| 404 page | `i looked for this page — it's not in my notebook. [back to your readings →]` |
| 500 page | `something tore. it wasn't your fault. [try again]` |
| Logout | `see you next trip.` (toast, fades, on /login redirect) |
| Maestro/LLM offline banner (sitewide) | `running slow today — the source desk isn't picking up. you can still browse old readings.` |

---

## The 5 phrases that are banned

These will appear by accident if anyone copies from a SaaS app. Catch
them in code review.

1. `Submitting…`
2. `Loading…`
3. `Powered by AI`
4. `Running` / `Complete` / any status word as a noun-pill
5. Any sentence starting with `Our` ("Our agent…", "Our system…")

If you find yourself reaching for one, rewrite in voice or just leave
blank — silence is more on-brand than corporate filler.
