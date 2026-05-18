# Plus One — Direction Options

> Decision document. Originally written 2026-05-14 in response to:
> *"is the editorial-luxury direction actually right, or is it
> skeuomorphism?"* Then updated the same day after user feedback that
> all of A/B/C still felt **too "AI-tool"**.
>
> Reading order:
> 1. **Part 1** — original critique of the very first draft
> 2. **Part 2** — directions A / B / C *(now deprioritized; kept for
>    reference only)*
> 3. **Part 3** — *(superseded by Part 5; skip)*
> 4. **Part 4 — Anti-AI directions D / E / F / G**, the live set
> 5. **Part 5 — Defended recommendation**

---

> ### ⚠ Status — A / B / C deprioritized
>
> User feedback after seeing A/B/C: all three **still felt like
> "AI tools"**, just dressed differently — the chrome (status pill,
> "live" badge, "depth 2/4", "Controller said:") gave the agent away
> in every variant. B was the worst offender (literally showed a
> Bloomberg-instrument view of the cycle); C was second (Things-3
> tool feel); A was the most disguised but the marginalia column still
> read as a debug log in pretty type.
>
> The new D / E / F / G set below is built on a different premise:
> the **agent is hidden** and the **SSE feed speaks in human voice**
> — no stage names, no depth numbers, no `running` / `complete`
> pills. The copy itself becomes the design surface.

---

## Part 1 — Honest critique of the editorial-luxury direction

The first draft (DESIGN_SPEC.md, mockups/*.html) committed to a
*Cereal-magazine-meets-Aesop* vocabulary: paper-white, ink, single brass
accent, generous whitespace, serif display, hairlines instead of shadows,
muted herbarium status palette. It is internally consistent and shippable.

It is also, on reflection, **partly wrong** for this product. Here is the
honest accounting:

### Where editorial-luxury actually fits Plus One
- **Trust signaling**. Reddit-and-XHS scraping needs the product to feel
  *considered*, not *casino-extracted*. Editorial does that. A purple
  gradient SaaS would actively hurt the trust pitch.
- **Anti-tourist-trap positioning**. The product's pitch is *quiet
  sources, not sponsored slop*. A loud UI would contradict that.
- **The output is genuinely literary**. A report card with a 3-paragraph
  prose explanation, two embedded source quotes, and a disagreement
  callout is structurally a magazine sidebar. Treating it as one is honest.
- **Display serif on report titles** earns its keep — the headline
  *"Menya Saimi"* set in Fraunces reads with intention. That isn't
  skeuomorphism; that's typography doing work.

### Where editorial-luxury is wrong for Plus One

These are the parts where I leaned on the print metaphor past the point
where it served the product.

1. **The SSE progress feed.** I drew it as a *literary marginalia
   timeline* — vertical hairline, monospace tags, italic Fraunces quote
   from the Controller. That looks beautiful, but it pretends the agent's
   thinking is a *finished artifact* (the way a printed book displays
   footnotes). It is not. It is *live*. The two seconds where a user
   watches "JOINER · depth 1 — cross-validating evidence" tick into
   existence is the **single most valuable trust moment** in the product.
   I treated it like a footnote when it's the show.

2. **The 90-second wait.** Editorial-luxury treats waiting as
   *contemplative*. For a planning tool the user might come back to from
   a different tab, contemplative wait time is just *wait time*. I have
   no progress percentage, no preview-while-loading, no "we found 7
   places already, here's the first one." The vibe takes precedence over
   the user's anxiety.

3. **Mobile-while-traveling is forgotten.** PRD §2 mentions the user is
   *planning*, but Batch 2g and the core PRD make it clear the report
   gets re-opened **on a phone, in Tokyo, at noon**, when the user
   wants to know "is this ramen-ya the gem from the report or not."
   Editorial-luxury report cards are gorgeous to read at a desk and
   slow to scan one-handed at a counter. The information density on
   mobile is too low.

4. **The "muted herbarium" status palette is a vanity choice.** Sand /
   atlas-blue / moss / terracotta is internally pretty, but `running`
   should *visibly demand attention*. A user opening their phone to
   check a trip wants to know "is it done?" in 100ms; my running-pulse
   is an opacity tick on a 6-px dot. I optimized for *not alarming
   anyone* when the actual job is *informing them quickly*.

5. **No room for the Chinese typographic case.** Half the user base is
   Chinese-speaking. Fraunces is Latin-only at display sizes; the spec
   says nothing about how 「東京」 sets next to "Tokyo." That's a
   real product hole, not a polish item.

6. **Skeuomorphism diagnosis.** The dead giveaway: the editorial mockup
   tries to make Plus One look like *the publication you would receive
   in the mail describing your trip*, when in fact it is *the live
   agent doing research and producing that publication*. Two different
   things. Designing for the artifact at the expense of the activity is
   the classic mistake.

### What I would keep regardless of direction
- Display-serif on **report titles only** (it's earned for content
  cards, not for chrome).
- Hairlines as the primary structural element (never shadows for the
  product surfaces).
- Source-quote-as-evidence as a first-class component.
- Per-card per-person match scores rendered as small bars.
- The disagreement card as a distinct visual category.
- The decision to NOT use traffic-light status colors is right; I just
  picked the wrong replacement palette.

---

## Part 2 — Three directions

Each of these is a **distinct bet on what Plus One is**, not three
flavors of the same idea.

| | **A. Editorial Atlas** | **B. Live Atelier** | **C. Field Notebook** |
|---|---|---|---|
| Bet on what PO is | A travel publication | The agent at work, live | A working tool you carry |
| Primary metaphor | Printed atlas / Cereal | Atelier / studio in motion | Field journal / Things 3 |
| Hero surface | Report (the artifact) | SSE feed (the activity) | Trip card list (the workflow) |
| Mobile priority | Read at desk first | Watch live first | Carry-in-pocket first |
| Density | Generous | Dense, layered, layered again | Dense, warm, dense |
| Accent color | Single brass | Cobalt + warm white-on-graphite | Persimmon + indigo |
| Risk if wrong | Skeuomorphism (above) | Looks like Perplexity / "another LLM UI" | Looks like every productivity app |

Each direction below has positioning, refs, color/type, SSE feed, report
cards, pros/cons, and an HTML sketch at
`docs/design/mockups/options/{a,b,c}-trip-detail.html`.

---

### Option A — **Editorial Atlas** *(the current direction, refined)*

#### Positioning
Plus One is a *publication you commission*. The agent is invisible;
what you receive is a small, considered atlas of one place, written for
you and your companions.

#### Refs
Cereal Magazine, Aesop, MUBI Notebook, *Wallpaper\* City Guides*,
**Monocle** small-format guides, Phaidon photo monographs.

#### Color
Paper `#F4F0E8`, ink `#15181F`, brass `#937642` (single accent).
Status uses the muted herbarium ramp **plus** an "active brass" running
state — when the cycle is live, the *running-pill* itself uses brass
fill (not a dot pulse), so the live-ness reads at glance.

#### Type
Fraunces (display) + Inter Tight (body) + JetBrains Mono (event tags).
**Adds**: Source Han Serif (Chinese display) + Source Han Sans (Chinese
body) — explicit pairing with Fraunces/Inter optical weights so 「東京」
and "Tokyo" set together cleanly.

#### SSE feed
**Reframed**: not a vertical-line *log*, but a *typesetter's
margin-note column*. The right gutter of the page fills with marginalia
*as the report itself begins to compose in the main column*. The user
watches the magazine literally being set in real time. This solves the
"agent thinking is the show" problem without abandoning the editorial
metaphor.

```
┌────────────────────────────────────────┬───────────────────┐
│ ─── READING TOKYO ───                  │ ●  PRODUCER       │
│ Tokyo.                                 │    pulling 12     │
│ for Yuna and Wei.                      │    candidates     │
│                                        │                   │
│ TL;DR (composing…)                     │ ○  JOINER         │
│ ┃ Lean into Sugamo and Jimbocho.       │    7 confirmed    │
│ ┃ Skip Shibuya for food. ▎             │                   │
│                                        │ ●  CONTROLLER     │
│ — Together —                           │    "need ZH       │
│ ▌ Menya Saimi (composing…)             │     disagreement  │
│   Sugamo · 12 sources                  │     signals"      │
│                                        │                   │
│                                        │ depth 1/4 · 00:31 │
└────────────────────────────────────────┴───────────────────┘
```

#### Report cards
Same as current, with a real fix: cards collapse to a **dense scan-mode
card** on mobile (title + 1-line dek + match-bars + sources count, no
prose) by default; tap to expand prose. Solves the "phone in Tokyo"
problem without losing the desk-reading feel.

#### Pros
- Visually unforgettable. Reads as a real product with a point of view.
- Lines up with anti-tourist-trap positioning.
- Display-serif report titles are earned typography.
- Marginalia reframe gives the SSE feed a job inside the metaphor.

#### Cons
- Still expensive to build (custom typesetting layout, Source Han Serif).
- Risk: looks pretentious to the wrong reviewer.
- Still slow to feel "active" — even with brass, the personality is *quiet*.
- Chinese typography parity is real work, not free.

#### Sketch
`docs/design/mockups/options/a-trip-detail.html`

---

### Option B — **Live Atelier** *(AI-native, but not chat-clone)*

#### Positioning
Plus One is **the agent at work, in public**. The product is a window
into a small studio where two analysts (one reading Reddit, one reading
Xiaohongshu) compare notes in front of you, and a third synthesizes.
The report is what falls out at the end — it isn't the show.

#### Refs
Linear's progress UI, Stripe's payment-flow inspector, **Perplexity Pro
Search** (the *trace* view, not the chat bubble), **Vercel v0** mid-build,
**Bloomberg Terminal** (typographic density, monospace+serif).
Crucially: NOT Claude.ai chat, NOT ChatGPT — those are conversational,
Plus One isn't.

#### Color
Background graphite `#161A1F`, on a warm-white reading surface
`#F2EEE7` for the report only. Accent: cobalt `#3556CC` (live signal,
links, reasoning highlights). Per-source brand-color dots (Reddit
orange, XHS red, Google blue) — this is one direction where source-
provenance gets to be loud, because the *dual-language receipts* are
the trust pitch and the colors do the work.

#### Type
**Tiempos Headline** (or *Newsreader* free) for display — looks like
serious financial-press serif, no Cereal-prettiness.
**Inter** (yes — *here* it earns its keep, because density+legibility>character).
**JetBrains Mono** as a first-class type, not just for event tags —
used for tags, source IDs, depth indicators, timer. This product
*should* feel a little like a Bloomberg terminal that produced an
elegant brief at the end.

#### SSE feed (the hero)
This is the entire screen during the cycle. Three vertical "lanes" —
**Reddit** (left, orange tick marks), **Xiaohongshu** (right, red tick
marks), **Synthesis** (center, cobalt). As the cycle runs, candidates
appear as small typeset cards in the side lanes; the Joiner draws
hairlines *between* matched candidates ("Menya Saimi appears in both,
strongest evidence: r/ramen + xhs:tokyo:ramen"); the Controller adds a
center-lane reasoning quote in serif italic. The report assembles
*center-out*, with the sourcing rails visibly converging into it.

```
REDDIT          ·     SYNTHESIS     ·          XIAOHONGSHU
                │                   │
[r/ramen]        ╲   ●●●  Menya  ╱  [小红书 拉面]
"thin broth..."  ──→ Saimi   ←──   "最安静的拉面店"
                │   12 sources     │
[r/JapanTravel] ╲    ●  Tsukiji   ╱  [小红书 东京]
"essential!"     ─────  ⚡  ────── "不是本地人会去"
                │ DISAGREEMENT     │
                │                  │
              CONTROLLER · depth 2 · 00:31
              "need ZH disagreement signals on Tsukiji"
```

When the cycle completes, the *rails compress to the right edge*
(remaining visible as a thin source-provenance gutter the user can
glance back at), and the report takes the center.

#### Report cards
Dense, structured, **terminal-grade** with tabular numerals everywhere.
Each card has a small "evidence breakdown" microviz (Reddit count vs
XHS count as two stacked bars) — you can see at a glance which
community is doing the talking on a given place. Disagreement cards
get a literal split-column layout: EN sources left, ZH sources right,
center band shows the disagreement axis.

#### Pros
- The SSE feed becomes the *defining* moment of the product. Anyone
  shown a screenshot of the live cycle will remember it.
- Matches the actual product nature (live agent, structured output).
- Source provenance becomes load-bearing visual, not decorative.
- Honest about what the product is.
- Information density wins on mobile: every pixel earns its keep.
- Differentiated from BOTH editorial-luxury and AI-chat-clone.

#### Cons
- Heaviest engineering lift for the SSE feed (the dual-rail composition
  is real work).
- Less "high-end" / 高级感 than option A. User asked for 高级感.
  *Mitigation*: this direction has its own kind of 高级感 — the
  Bloomberg / Tiempos register reads as *serious-instrument*, not
  *consumer app*. But it's a different flavor.
- Risk of feeling cold / engineering-y to non-technical users.
- Dark-default UI is a commitment.

#### Sketch
`docs/design/mockups/options/b-trip-detail.html`

---

### Option C — **Field Notebook** *(utility-first, mobile-native)*

#### Positioning
Plus One is *the small leather-covered Moleskine you take on the trip*.
On the desktop you fill it in; on the phone you carry it. The agent is
politely backgrounded — it does its job and returns a tool, not an
artifact. The tool is the surface.

#### Refs
Things 3 (the iOS app — restraint with personality), **Day One**
journal, **Bear**, **Linea Sketch**, **Field Notes** notebooks,
**Atlas Obscura** (warm-but-utilitarian editorial), **Maps.me** (offline-
first travel utility).

#### Color
Cream `#F8F4EC` paper, warm dark `#231F1B` ink. Accent: persimmon
`#D45A2C` (used for the "you-are-here" / actionable / live signals)
and indigo `#2A4170` (used for ZH-source provenance and saved-for-later).
This is a *warm* palette — not luxurious-cold like editorial, not
graphite-cold like atelier. Status uses the persimmon for `running`
(a single visible orange dot demands attention), moss `complete`,
pencil-grey `pending`, dim red `aborted`.

#### Type
**Söhne** or its free cousin **Geist** for body — the warmth + workhorse
combination of a notebook hand. **Reckless** (display, free OFL) for
the headline-serif voice — it's a more *handwritten-feeling* serif than
Fraunces. **iA Writer Mono** for SSE tags. The type wants to feel like
"nice handwriting in a nice notebook" without being literal-handwriting.

#### SSE feed
Lives in a small **status drawer at the top of the page** — not a hero
surface, deliberately. The drawer shows a 3-state condensed timeline
(Reading sources → Cross-checking → Composing), with a thin orange
progress bar underneath. Tap to expand into the full event log if the
user wants the detail; otherwise it stays out of the way and the report
*streams in below it as it's ready* — top-most card first, additional
cards appearing below.

```
┌────────────────────────────────────────────┐
│  Tokyo   for Yuna and Wei                  │
│  ─────────────────────                     │
│  ●─●─○─◇   Reading · 12 → 7 · composing   │ ← drawer
│  ▰▰▰▰▰▰▱▱▱▱   00:31 / ~01:30 · tap for log│
├────────────────────────────────────────────┤
│  ★  Menya Saimi    · Sugamo  12▮ ✓       │ ← cards stream in
│     Quiet shio counter, no English menu.   │
│     [Yuna 0.78][You 0.91]  → save  share   │
│  ─                                         │
│  ⚠  Tsukiji Outer Market · Chuo  28▮ ✗   │
│     EN says essential, ZH says set-piece.  │
│     → see both sides                       │
│  ─                                         │
│  composing more…                           │
└────────────────────────────────────────────┘
```

#### Report cards
Closer to **list rows than magazine spreads.** Title + 1-line dek +
neighborhood + source-count + match-score row, all in a 2-line height.
Tap or hover expands inline to show prose + sources strip. This is the
"phone in Tokyo at noon" mode by default; the desktop just gives more
horizontal space for the row, not a different design.

Strong **save / shortlist / route-to** verbs on every card — Plus One
becomes a *working set* the user curates, not just a thing they read
once. (This is also where v2 features land naturally — shortlist
becomes a day-by-day arrangement.)

#### Pros
- Honest about how the product is actually used (planning AND traveling).
- Mobile experience is by far the strongest of the three.
- Streaming cards-as-they-finish is genuinely better UX than waiting
  90s for everything.
- Persimmon `running` is *visibly* live without being garish.
- Lowest design risk; closest to ship.
- Easy v2 path (shortlist → itinerary).

#### Cons
- Loses the most 高级感 of the three. User explicitly asked for it.
  *Mitigation*: a *very well done* notebook (Things 3 quality) is a
  kind of luxury, but a different one — this is the **Aman-of-utility**
  bet, not the Aman-of-aesthetics bet.
- Less memorable in a screenshot. Will look at first glance like
  "another travel app," and the depth only reveals itself in use.
- The print-publication moment that makes editorial-luxury *feel
  expensive* is gone.
- Streaming cards is real engineering work too (frontend has to
  partial-render the report as events arrive).

#### Sketch
`docs/design/mockups/options/c-trip-detail.html`

---

## Part 3 — My recommendation, if asked

If the user genuinely values 高级感 above all other axes: **A (refined)**.
The marginalia reframe fixes the worst of the original critique and the
mobile scan-card fix solves the worst of the second-worst.

If the user values **honesty about what the product is** over genre:
**B (Live Atelier)**. This is the option that *makes the SSE feed earn
its USP status*, and it's the most differentiated from anything else
in market right now. It is the one I personally lean toward for this
specific product, with the caveat that it is the highest-risk and the
least 高级感-as-traditionally-defined.

If the user wants the **product to actually win on use** (Phase β
metrics — top 10 user issues fixed, satisfaction): **C (Field
Notebook)**. The other two are more designed; this one is more *used*.

A real fourth option exists — **A's typography + B's SSE + C's
streaming cards** — but I'm declining to propose it as a fourth column
because it's the kind of "everything good" hybrid that loses both
internal consistency and the discipline of *committing* to a bet. If
the user picks one of A/B/C and wants to selectively borrow, that's
fine to do as a follow-up; pretending there's a free hybrid up front is
a way to dodge the actual choice.

---

## Files

- This document: `docs/design/DIRECTION_OPTIONS.md`
- Option A sketch *(deprioritized)*: `docs/design/mockups/options/a-trip-detail.html`
- Option B sketch *(deprioritized)*: `docs/design/mockups/options/b-trip-detail.html`
- Option C sketch *(deprioritized)*: `docs/design/mockups/options/c-trip-detail.html`
- **Option D sketch:** `docs/design/mockups/options/d-trip-detail.html`
- **Option E sketch:** `docs/design/mockups/options/e-trip-detail.html`
- **Option F sketch:** `docs/design/mockups/options/f-trip-detail.html`
- **Option G sketch:** `docs/design/mockups/options/g-trip-detail.html`
- Original A long-form spec: `docs/design/DESIGN_SPEC.md`
- Original A 7-page mockup set: `docs/design/mockups/`

The original 7-page mockup set is *not deleted* — it remains as the
fully-realized version of A so the user can compare A's depth against
the single-screen sketches of B–G honestly.

---

## Part 4 — Anti-AI directions (D / E / F / G)

User pushback after A/B/C: *all three still felt AI-tool*. The chrome
betrayed the agent in every case. The four directions below all share
two non-negotiable constraints:

1. **The agent is hidden.** No `producer` / `joiner` / `controller`
   stage names. No `depth 2/4`. No `running / complete / aborted`
   pills. No "live" badges that call out the LLM nature.
2. **The SSE feed is human voice.** Every line of progress copy is
   written *as a person would speak it*, in that direction's voice
   register. The copy itself is the most distinctive design surface
   of each direction.

The same backend events get spoken four very different ways.
The voice copy for each is listed in full below — that's what makes
each direction what it is.

---

### Option D — **Scrapbook / Handcraft**

#### Positioning
Plus One feels like *a friend's travel notebook* opened on the table
between you. Photo-corners, washi tape, tickets, hand-scrawled
captions next to printed ramen-shop names. The agent vanishes
completely; what's left is the *evidence of someone having gone and
collected this for you*.

#### References
Moleskine travel notebooks; Japanese 旅ノート / journaling culture;
*Field Notes* memo books; early Pinterest moodboards; Wes-Anderson-
adjacent props; the TripIt notebook era.

#### Color
- Substrate: aged paper `#ECE4D2` with subtle SVG-noise grain and
  a vignette darken at the edges
- Inks: ink `#2A241B`, pencil grey `#8C7B5E`, sepia `#7A4F22`,
  red marker `#B94335`
- Washi-tape accents: mint `#BCD4C0`, blue `#A8B8C8`, yellow
  `#E8D27A` (not used as fills — only as taped corners and sticky
  notes)

#### Typography (with rationale)
- **Caveat** for the dominant handwritten voice — feels like a felt-
  tip pen, has the right looseness to *not* read as system UI.
- **Kalam** for secondary handwriting — slightly more compressed,
  used for annotations so the eye distinguishes "title scribble" from
  "side note" without thinking about it.
- **Special Elite** for the typewriter voice — used for stamps,
  dates, station codes, anything that *should* feel printed by a
  machine (vs. handwritten by a person).
- **Shippori Mincho** for Japanese place names — pairs better with
  Caveat than the more rigid Noto Sans CJK does, and lends a
  *literary travel-essay* quality to 「築地」 and 「麺屋彩未」.

The point of this pairing: every glyph on the page is either *clearly
written by a person* or *clearly stamped by a tool*. Nothing is
"app sans-serif", which is what gives an interface its AI smell.

#### SSE voice copy (full)
1. `asking around on reddit. people are loud here, takes a sec to find the quiet ones.`
2. `some of these come up twice — saving the doubles.`  *(annotated:* `menya saimi appears in 12 different threads ★`*)*
3. `now checking 小红书 for the same names. cross-referencing.`
4. `two of them disagree about tsukiji. interesting — going one more round to figure out which side is right.`
5. `doing one more pass — there's a quieter version of ichiran someone keeps mentioning.`
6. `tying it all together now.`
7. `final sticky note: ~ 60s left. stay if you want — i'll ping when done.`

The voice is *informal first-person*, lowercase, present-progressive,
with little asides scrawled in red marker next to the main lines.
Reads like a friend texting you while they're doing the work.

#### Report cards
Photo-card with photo-corner tape, hand-written caption underneath,
a red-marker verdict scrawled across the bottom-right. Tickets and
receipts for disagreement entries (perforated dashed line down the
middle, "DISAGREEMENT NOTED" stamp). A scrap-paper TL;DR taped to the
left margin. Each card is *slightly tilted* (`rotate(-1.5deg)`,
`rotate(2deg)`) so the page never feels grid-locked. Hover un-tilts
and lifts — like picking up a polaroid.

#### Pros (for Plus One specifically)
- **Completely unmistakable.** Nobody confuses this for any other
  travel app. Memorable in a screenshot.
- **The 90s wait becomes charming.** Watching a friend scrawl
  notes is *fun*; watching an agent run is *tedious*. This direction
  re-frames the wait as a feature.
- **Anti-tourist-trap positioning is structural,** not a tagline.
  A handwritten notebook *can't be sponsored content* — the form
  signals authenticity.
- **Mobile feels native** because the language of phones-as-cameras
  *is* photo-corner / sticker / sticky-note. iOS Notes, Day One,
  Polarsteps already use this vocabulary.
- **Handles dual-language gorgeously.** Japanese characters in
  Mincho next to handwritten English caption already looks like a
  travel notebook from Tokyo, not a translation glitch.

#### Cons
- **Real risk of "twee".** If executed badly this becomes
  Tumblr-2014 / a wedding website. Requires discipline to keep the
  hand-elements *spare*; one sticker too many tips it.
- **Accessibility cost.** Caveat at body-size is hard to read for
  some users — needs a "switch to printed" toggle, not just a
  reduced-motion toggle.
- **Authoring cost in code.** Hand-tilted cards, washi-tape
  positioning, photo-corner SVGs, paper-grain textures — all real
  work, much of it not Tailwind-utility-class friendly.
- **Doesn't scale to a thousand users.** Hand-feel reads as
  "made for me"; once it's clearly mass-produced (by an LLM, no
  less), the metaphor strains. Mitigation: lean into per-user
  handwriting variety (random tilt, random tape colors, slight
  word-spacing jitter) so no two users see the same notebook.

#### Sketch
`docs/design/mockups/options/d-trip-detail.html` — mid-cycle: three
findings settled (Menya Saimi photo-card, Tsukiji disagreement
ticket, Ichiran skip-card) plus a TL;DR scrap, plus the *scratchpad*
on the right with three completed dispatches and one currently
arriving with animated dots.

---

### Option E — **Printed Page (Monocle / MUJI)**

#### Positioning
Plus One presents as *a single issue of a small printed magazine* —
asymmetric editorial grid, a hierarchy of section bars, a nameplate
across the top. The agent doesn't appear because *magazines don't show
their authoring process*; what runs in real time is **a series of
quiet section subtitles**, the way a magazine masthead might print
"now reading: Reddit threads from the last six months."

#### References
*Monocle*, *Wallpaper\**, *Apartamento*, MUJI paper goods, Penguin
Modern Classics, *Real Review*, *The Gourmand*, Werkplaats Typografie
catalogues.

#### Color
- Substrate: warm cream `#FBF9F4` (not the cooler editorial
  paper-white of A) — feels like *MUJI recycled paper*
- Inks: ink `#1A1A1A`, ink-2 `#4A4A4A`, ink-3 `#888378`,
  rule `#D8D2C0`
- **One signal red:** `#C84A1F` (the Monocle red — used only for
  section bars, kicker dashes, the live-bug position) and a
  single `#4F6B47` muted green for "confirmed."

#### Typography (with rationale)
- **Source Serif 4** (free, opsz axis) for display & long body
  lede — Tiempos-quality serif at zero licensing risk; the optical-
  size axis means standfirsts and big H1s can use the *display* cut
  while body uses the *text* cut, the way a real magazine sets type.
- **Plus Jakarta Sans** for UI body and short captions — friendlier
  than Inter, with an editorial-MUJI quietness; not a workhorse
  grotesque (Inter), not a personality face (Söhne) — the *quiet
  middle* that magazines actually use for section text.
- **Roboto Mono** for the section-bar labels, dates, page numbers,
  and the SSE timestamps — feels *printed*, not *terminal*.
- **Noto Serif JP** matched in weight to Source Serif 4 so 「東京」
  sits perfectly with "Tokyo" without a baseline jump.

The pairing reads as *small-press magazine*: a long-form serif you
read, a quiet sans you scan, a mono you ignore (timestamps,
page numbers, etc).

#### SSE voice copy (full)
1. `Scanning Reddit threads from the last six months.`
2. `Filtering recommendations that appear in more than one source.`
3. `Comparing Chinese-language posts on Xiaohongshu against the English ones.`
4. `Two contested entries identified. Reading further.`
5. `Refining the shortlist.`
6. `Composing the report.`

Voice register: **Monocle subtitle voice.** Sentence case, no
exclamation, no first-person, declarative present-progressive,
reportorial. Each line could appear as a kicker under a printed
photograph. The fourth line introduces a *finding* (two contested
entries) the way a print magazine sub-head would.

The lines display as a numbered ordered list (`01`, `02`, `03`,
`04` in mono) inside a "Dispatches from the reading" section bar.
No status pills, no live badge — the section bar itself says
*"Dispatches from the reading"* and that's enough. The currently-
arriving line is set in italic Source Serif and has a quietly
animated trailing dot.

#### Report cards
**Asymmetric editorial grid.** A one-and-a-half-column hero card
with a photograph; smaller cards on a 3-up grid. Each card has a
mono kicker (`Together · 12 sources`), a serif name, a
mono `place line`, a serif lede paragraph, and a hairline-bordered
figures row at the bottom (`You 0.91 / Yuna 0.78 / Wait ~10 min`).
*Composing* cards live in the same grid as published cards — they
just have a softer background and italic placeholder copy. The grid
doesn't reflow when a new card lands; only the card's content
materialises in place. (This is what makes it feel like a *layout*,
not a feed.)

#### Pros (for Plus One specifically)
- **Earns 高级感** without leaning on luxury-hotel tropes — closer
  to *editorial credibility* than *aspirational lifestyle*.
- **The agent is *invisible* by design.** Magazines don't show their
  copy editors. The "Dispatches" section reads as a section, not a
  log.
- **Asymmetric grid scales beautifully** to long reports — adding
  more places doesn't mean adding more cards in the same shape, it
  means giving the whole report more rhythmic variety.
- **Mobile collapse is straightforward** because magazines have
  always had to do single-column reflows for *iPad / phone*
  editions; the grammar already exists.
- **Source Serif 4 + Noto Serif JP** is a real, well-paired
  bilingual system — costs nothing, looks like ¥50,000 spend on
  a custom typeface house.

#### Cons
- **Risk of "looking like every editorial template."** The Cereal /
  Wallpaper grammar is now common enough that a sloppy execution
  reads as *generic-magazine-template*. Differentiation has to come
  from copy voice + photography choice.
- **Photograph dependence.** Every report needs at least one strong
  hero image; without it the layout dies. We don't have a photo
  source plan yet (Unsplash? scraped from sources? AI-generated?
  user-uploaded?). This is a real hole.
- **Less "live" feeling.** A magazine running in real time is a
  conceptual contradiction the user has to accept. Some won't.
- **Loses the warmth that D has** in spades — this is *cool*
  editorial, not *intimate* editorial.

#### Sketch
`docs/design/mockups/options/e-trip-detail.html` — full magazine
layout: nameplate masthead, section bars, hero photograph + meta,
the Dispatches section with all four voice-lines (last in italic),
asymmetric findings grid with three published cards + two composing
cards in-grid, colophon at the bottom.

---

### Option F — **Brand Brochure / Hotel Site**

#### Positioning
Plus One presents as *a small luxury brand commissioning a reading
on your behalf.* The page reads like an Aman or NoMad property page:
full-bleed photograph, restrained capitals navigation, italic
standfirst, recommendations described as *"suites"* (rooms in the
brochure), a concierge writing you a personal note while it's all
being prepared. The agent vanishes behind a *human concierge persona*
who narrates progress in soft second-person.

#### References
Aman, NoMad, Soho House, The Standard, *Cereal Travel* booklet,
Apartamento city guides, Acne Studios FW campaign pages, *Toast*
catalog, Hermès journal pages.

#### Color
- Substrate: bone `#F4EFE3` and warm sand `#E8E0D0` (overlapping
  panels)
- Inks: night `#1F1B17` (warm near-black), warm `#6E5C42`,
  rule `#D8D2C0`
- **Single accent:** brushed gilt `#B89B6A` — used for the dot in
  the wordmark, the kicker dashes, the seal border, the live-arrival
  dot, italic "arrange this" links. Never a fill; always an
  intervention.
- A **night-tone hero** (full-bleed photograph) anchors the top of
  the page; everything below sits on bone.

#### Typography (with rationale)
- **Cormorant Garamond / Cormorant Infant** for display &
  long copy — old-style Garamond proportions, tall ascenders, an
  *italic* that earns its keep (the standfirst is in Cormorant
  Infant italic, lighter and rounder than the upright). The
  Garamond reading register is *the* hotel-brochure voice; it
  reads as *generations old*, not *six months old*.
- **Inter** *(yes, Inter — but only at 11px caps)* for nav, eyebrow,
  micro-meta. Inter is the right choice when the type job is
  *recede entirely* so the serif can sing. Letter-spaced to 0.32em,
  weight 400, all-caps.
- **Noto Serif JP Light** for Japanese — matches Cormorant's
  optical weight better than the regular weight.

This is a **serif-dominant system**, the opposite of B (sans-
dominant). The sans is so quiet it's almost watermark; everything
the user reads is set in Cormorant.

#### SSE voice copy (full)
1. `We're listening to what locals are quietly recommending.`
2. `Several names keep coming back — we're noting those first.`
3. `Now reading the Chinese travel community on the same places.`
4. `Where they disagree with the English sources, we'll show you both sides.`
5. `Setting aside the spots that only sound good in promotional copy.`
6. `Bringing it all together for you.`
7. *(sign-off, after each line lands):* `— with care, Plus One`

Voice register: **second-person concierge.** "We" and "you," never
"I". Every line is what a hotel host or boutique-shop attendant
might say if narrating their work for you. The fourth line is the
*service moment* — explicitly framing disagreement as *something
done on your behalf* rather than *something the system noticed*.

The lines display as **a numbered letter** inside a "concierge
note" card that overlaps the hero. Numbered `01–04` in light-gilt
small caps; the body in upright Cormorant; the currently-arriving
line in *italic Cormorant Infant* with a soft animated trailing dot.
A "— with care," signature in italic at the bottom.

#### Report cards
**"Suites" pattern** — each recommendation is a 50/50 photograph +
text composition. Photograph on one side, kicker dash + name +
place + body paragraph + a hairline-bordered "meta-row" + an italic
"Add to your itinerary →" link on the other. Alternates direction
(photo-left, photo-right) like an Aman suite gallery. Hover gently
zooms the photograph 4% over 1.2s. Composing entries get a
sand-gradient placeholder where the photograph would be, with
*"photographing now…"* in italic.

#### Pros (for Plus One specifically)
- **Earns the highest 高级感 of any direction here.** This is the
  only one where a luxury brand could plausibly send the URL
  unchanged.
- **Concierge framing solves the "AI tool" problem completely.**
  The voice IS a person, even if everyone knows it isn't. The
  product never claims *I'm an AI agent*; it adopts a character.
- **The 90-second wait becomes anticipation,** not loading.
  Hotel-brochure pacing makes the user *lean in*, not *get
  impatient*.
- **Photography-first plays to travel UX strengths** — the user
  wants to see the place before reading about it.
- **Bilingual handles gracefully** because hotel brochures already
  accept multi-language as a baseline.

#### Cons
- **Largest gap between vibe and product reality.** A free-tier
  user-facing tool dressed as a $2,000-a-night brand will read as
  pretentious to many users — particularly the cynical
  Reddit-reading audience PRD §2 names. There's a real risk of
  *eye-rolling*.
- **Photograph dependence is acute.** Every recommendation needs
  one good photograph. Without a clear photo source plan this
  direction collapses on the first card.
- **Doesn't scale to "Tokyo at noon, on a phone, hungry."**
  Brochure-pacing is *deliberately* not utilitarian. The same trip
  detail that's beautiful at home is annoying when you're trying
  to decide whether to walk three blocks for ramen.
- **Concierge voice can feel saccharine** if not policed —
  "with care," signing a numbered letter every reading is a knife-
  edge. Sample 7 had to come out before showing the user.

#### Sketch
`docs/design/mockups/options/f-trip-detail.html` — full hotel-page
composition: capitals nav, full-bleed Tokyo dusk hero with kicker
+ Cormorant H1 + standfirst, an overlapping concierge-note card
with circular seal + numbered letter (4 lines, last italic) +
"with care," signoff, then "The findings, so far" suite gallery
with three photographed entries (alternating photo-left / photo-
right) + one composing entry, dark footer.

---

### Option G — **Vintage Exploration / Map Journal**

#### Positioning
Plus One presents as *a 1930s travel-bureau report from a
correspondent in the field*. Parchment substrate, hand-drawn
district map with stamped pins and a dotted route, telegram-style
SSE feed in monospace ALL CAPS with `STOP.` punctuation, three
rotating ink-stamps in the masthead, logbook entries with red
marginal pin-dots and corner Roman numerals. The agent disappears
because *the metaphor is "a person filing dispatches from Tokyo"*
— who, by 1930s convention, is *understood to be a real person*.

#### References
Atlas Obscura, Wes Anderson stationery (Grand Budapest, Asteroid
City), mid-century Pan-Am / NYK Line travel posters, *Field Notes*
Brand notebooks, the Royal Geographical Society reports, vintage
National Geographic logos, Indiana Jones map sequences, the *Voyages
& Découvertes* genre.

#### Color
- Substrate: parchment `#ECDFC4` with parchment-edge `#E2D2B0`
  and an SVG-noise grain + radial vignette darken
- Inks: ink `#2A1F12`, ink-2 `#5A4528`, sepia `#7A4F22`
- **Three stamp colors** (one per stamp; rotated `-7°`, `+4°`,
  `-3°`): stamp red `#A53326`, stamp blue `#2E5273`, stamp green
  `#4F6B3A`
- **Gold pin** `#B58E3F` for "local gem" map markers
- **Route line** `#A53326` dotted, hand-drawn over the SVG map

#### Typography (with rationale)
- **IM Fell English (Italic)** for the display H1s — 1670s
  Oxford Press digital revival, has the *correct* historical
  irregularity for a 1930s-evoking page (paradox: 17th-c. type
  reads as "old" to modern eyes more readily than actual 1930s
  type does). Not gimmicky like a "vintage" font from a free
  bundle; this is a real revival.
- **IM Fell English SC** for small-caps section labels.
- **Old Standard TT** for body copy — Modern-style serif, very
  legible, calm — because IM Fell at body size becomes hard to
  read. This pairing is a discipline: *display gets the character,
  body gets the legibility.*
- **Special Elite** (typewriter face) for the **telegram dispatches
  on the left**, dates, station codes, and stamp interiors. This
  carries the 1930s mechanical-press voice.
- **Noto Serif JP** for Japanese place names — sits next to IM Fell
  better than Mincho, surprisingly, because both have similar
  vertical weight in the strokes.

The visual conceit: *handwritten / typewritten / printed-press*
strata are all visible at once. Like a real document collection.

#### SSE voice copy (full)
1. `LETTERS ARRIVING FROM r/JapanTravel — TWELVE SO FAR. STOP.`
2. `SORTING NAMES THAT APPEAR IN MORE THAN ONE DISPATCH. SEVEN STAND. STOP.`
3. `NOW OPENING THE XIAOHONGSHU POUCH — EIGHT NOTES FROM THE FIELD. STOP.`
4. `A DISAGREEMENT DETECTED — TSUKIJI. TWO SIDES TO HEAR. STAND BY.`
5. `ONE MORE SWEEP THROUGH THE WIRES.`
6. `FOLDING THE MAP.`

Voice register: **telegram / postcard.** All caps, monospace,
declarative comma-stops with `STOP.` punctuation, slightly archaic
("opening the pouch," "stand by," "folding the map"), *faintly
nautical*. Each dispatch is timestamped to the second
(`14:02:11`) like a real telegram. The arriving line has a
blinking-caret `▏` instead of an animated dot, because telegrams
got cut off mid-word.

The dispatch panel itself is styled as a *vellum telegram form*
with a perforated tape edge at the top, a "wire open" red border
indicator, and a "— folding the map in roughly one minute —"
sign-off in IM Fell italic at the bottom.

#### Report cards
**Logbook entries.** Each entry has a Roman numeral (`Entry I`,
`Entry II`), a red marginal pin-dot, a *small wax-stamp-style*
verdict in one of the three stamp colors (`Recommended` /
`Two sides` / `Avoid this branch`), an IM Fell italic name with the
Japanese set in Noto Serif JP, an Old Standard body paragraph, and
a typewriter-mono foot row with bold values
(`You match 0.91 / Yuna match 0.78 / Best weekday a.m.`). The
"composing" entry uses a 45° hatched parchment background and an
"arriving by next post" Roman numeral.

#### Pros (for Plus One specifically)
- **Most distinctive of all directions.** Genuinely no travel app
  alive looks like this. Screenshot-memorable.
- **The hand-drawn map is a feature**, not a fake. Travel UX has
  *always* wanted a map; this direction makes it a hand-drawn
  parchment one with dotted routes. We don't need Mapbox.
- **Telegram-voice handles the "AI feels alive" problem
  elegantly.** Telegrams *should* sound clipped and slightly
  inhuman; the ALL CAPS / `STOP.` register makes the AI's
  occasional weirdness *feel intentional*. This is the only
  direction where the AI's natural failure modes (clipped,
  truncated, factual) become aesthetic *strengths*.
- **Stamps and Roman numerals are dirt-cheap to implement** —
  borders + transforms + a couple of typefaces. Most of the cost
  is in copy + the hand-drawn SVG map (one-time).
- **Bilingual feels period-correct** — 1930s travel reports
  routinely included native-language place names.

#### Cons
- **The strongest "this is a costume" risk of all four.** A
  vintage/Wes-Anderson aesthetic on a 2026 product can feel
  *insincere* if the rest of the brand isn't all-in. Either commit
  fully (the email receipts also use IM Fell + parchment, the
  loading state is also a telegram) or it'll feel like a single
  cute screen.
- **Mobile is hardest of the four.** Parchment textures scale
  badly to small screens; SVG maps lose detail; ALL-CAPS
  monospace dispatches eat space.
- **Accessibility cost.** Parchment + sepia + low-contrast
  intentional fade is a real WCAG problem. Will need a
  high-contrast mode toggle from Day 1.
- **Risk of *too* romantic** — a 1930s frame on Reddit-and-XHS
  scraping has a slight tonal mismatch. The product reads
  contemporary sources; the wrapper says "expedition." Some
  users will find that delightful, some pretentious.
- **Hardest to evolve.** A magazine (E) can keep adding sections;
  a notebook (D) can keep adding pages; a hotel brochure (F) can
  add suites. *A 1930s telegram report* is a fixed genre — when
  v2 wants to add itinerary planning or calendar sync, the
  metaphor has nowhere to go without breaking.

#### Sketch
`docs/design/mockups/options/g-trip-detail.html` — bureau-letterhead
masthead with double-rule top/bottom, three rotated ink-stamps,
Tokyo + 東京 H1 in IM Fell italic, three-column body: vellum
telegram with four wire-style dispatches (last with blinking
caret), a hand-drawn SVG map with three color-coded pins + a
dotted route + a "surveying…" question-mark pin in Jimbocho, three
logbook entries (Recommended green / Two-sides blue / Avoid grey)
plus one hatched "arriving by next post" composing entry, double-
rule colophon.

---

## Part 5 — Defended recommendation

If I'm forced to pick one of D / E / F / G for Plus One specifically
— and the brief says I am — the answer is **D, Scrapbook /
Handcraft**, with one specific caveat I'll spell out.

### Why D, not the other three

**Why not F (Hotel Brochure).** F is the most beautiful sketch and
earns the most 高级感 in raw aesthetic terms. But it's wrong for
this product *demographically*. PRD §2 names the user as
"Chinese-speaking, 30–45, middle class, hates sponsored content."
The Aman/NoMad register is *aspirational luxury*; serving it to
someone whose explicit pain point is *anti-tourist-trap and
anti-sponsored* will read as **the thing they came here to escape**.
The concierge voice is also brittle: it works once, feels twee on
the third reading, and turns saccharine on the tenth. F is the
right pick for a different product (a Plus One Pro tier, a hotel
recommender, a curated-travel-agent positioning) — not the MVP.

**Why not E (Printed Page).** E is the safest pick and earns
genuine editorial credibility. But it has the **photograph problem
we don't have a solution to** (every report needs a hero image and
we have no source plan), and — more importantly — it's the
direction *most likely to look like another well-designed travel
magazine site*. Cereal does this. *Drift* does this. Apartamento
does this. *Plus One needs differentiation, not membership*.
Picking E would be picking a known-good design system, not a
distinctive product identity. E is the right pick if the user
later vetoes D as "too cute" and we need a respectable fallback.

**Why not G (Vintage Exploration).** G is the most fun sketch and
the most distinctive in a screenshot. But it has the
**evolution-cliff problem**: a 1930s telegram report is a *fixed*
genre. The day the v2 PRD adds itinerary planning or trip-
sharing-with-friends or calendar sync, the metaphor breaks
visibly — what does an itinerary planner look like in a 1930s
travel report? A train timetable? Shoehorn city. G is also the
hardest of the four for mobile (parchment textures) and for
accessibility (sepia contrast). G is the right pick for a
*single-shot demo product* that doesn't need to grow — exactly the
shape v1 is, but exactly the shape v2 will not be.

### Why D wins

D earns its place against F/E/G on **five product-specific axes**:

1. **The 90-second wait stops being a wait.** Watching a friend
   scrawl notes is *fun*; watching a magazine typeset is *neutral*;
   watching a hotel concierge prepare a brief is *anticipatory*;
   watching a telegram tick in is *cute, then slow*. D is the
   only direction that turns the load time into a feature instead
   of a tax.

2. **Anti-tourist-trap positioning is structural.** A handwritten
   notebook *cannot be sponsored content* — the form itself
   signals authenticity. F's hotel brochure signals the opposite.
   E's editorial magazine signals "respectability" but *some*
   editorial magazines are sponsored. G's bureau-report signals
   "expedition" but is theatre. Only D's form has the trust
   guarantee built into the medium.

3. **Mobile-while-traveling is the strongest** of the four.
   Phones-as-cameras-and-stickers is the native vocabulary of
   iOS Notes / Day One / Polarsteps. A user pulling out their
   phone in Tokyo to check "is this the spot from the report" is
   already in the mental model of *flipping through a notebook*.

4. **Bilingual lands gracefully.** Japanese characters in Mincho
   next to handwritten English caption is a legible, *travel-
   notebook-from-Tokyo* moment, not a layout problem to solve. E
   and F both handle bilingual *adequately*; D handles it
   *expressively*.

5. **The voice copy is the one a friend would actually use.** The
   D voice — "asking around on reddit. people are loud here, takes
   a sec to find the quiet ones." — is the only voice register of
   the four that *makes the AI claim less, not more*. F and E
   both promise more than the agent can deliver (F: a concierge
   who knows you; E: a magazine that fact-checked everything).
   G makes the same mistake, just in old-timey costume. D makes
   *the smallest authority claim of the four*, which is the right
   thing to do when the system is one Maestro outage away from
   `cycle_aborted`.

### The caveat — keep one knob from E

The **photograph-when-available** pattern from E is worth porting
in: when a place has a real Unsplash-or-source photo, D should let
the photo-card *be* a photo card; when it doesn't, D should fall
back to a hand-drawn icon-card or a typed-label card. This makes D
robust against the photo-source problem that kills E and F outright,
without abandoning D's core voice. (F and G do not get this
flexibility — they're photo-or-die.)

### What I'd ship if D is picked

1. A **production CSS for the notebook substrate** (paper grain
   SVG, vignette, baseline tilt jitter on cards via per-instance
   random `--tilt` CSS var, corner-tape positioning).
2. The **same 7-page mockup set** rebuilt in D's voice — login
   becomes "say hello," auth-exchange becomes "letting you in"
   in handwritten margin notes, profile becomes "about you" as a
   notebook insert page with sticker-tab category dividers.
3. **Voice-copy extension** to cover all 8 SSE event types
   (currently I drafted 4-6 per direction; D needs the full
   per-event human-voice corpus, including `cycle_aborted` —
   "hit a wall — couldn't get through to maestro. let's try
   again?" — and `iteration_start` etc.).
4. A **photo-or-typed-label fallback system** as above.
5. A **"switch to printed view" toggle** for accessibility (Caveat
   → Plus Jakarta + remove tilt + plain backgrounds).

### Confidence

I'm a 7/10 on this pick, not 10/10. The honest residual doubt is
that **D may not earn enough 高级感 for the user who explicitly
asked for it**. The user's first feedback round flagged the
original direction as *too tool-y*; the second flagged
A/B/C as *still too tool-y*. They have not yet flagged anything
as *too cute* or *too craft-y*, but they could reasonably do so
on D. If they do, the next pivot is **F with D's voice register
ported in** — concierge brochure but written like a friend, not
like a fragrance label. That hybrid is the genuinely-defensible
fallback if D fails the user-vibe test.
