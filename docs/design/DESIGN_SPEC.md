# Plus One — Design Spec

> Locked: 2026-05-14. Visual system for the Plus One web app.
> Target: editorial-luxury travel publication that happens to be an AI tool.

---

## 1. Brand positioning

**One sentence.** Plus One is a *quiet, literary* travel companion — closer to a
slim hardback guidebook than a SaaS dashboard.

**Three adjectives.** Considered. Patient. Unhurried.

**What we are not.** Not a chatbot. Not a feed. Not a "magic" sparkle-emoji
product. Not a map-first experience. Users come here to *read*, then go.

**Reference vectors** (use as compass, not copy-paste):
- *Cereal Magazine* — generous margins, editorial photography rhythm, serif headlines, tiny captions.
- *Aesop* — restraint, beige/cream/ink palette, taxonomy-as-design.
- *Aman Resorts* — confident silence, no exclamation marks, decisions feel inevitable.
- *MUBI Notebook* — long-form layout in a tech product.

**Anti-references.** Airbnb (too friendly), Hopper (too loud), Notion AI
(too generic), generic purple-gradient SaaS.

---

## 2. Type system

Two families. Both Google-Fonts-hosted so Tailwind/Next can ship them via
`next/font` without licensing fights.

| Role | Family | Notes |
|------|--------|-------|
| Display | **GT Sectra** (or fallback **Fraunces** opsz 144) | High-contrast modern serif. Used for trip titles, hero headlines, report card titles. |
| Body | **Söhne** (or fallback **Inter Tight**) | Neutral grotesque, warmer than Inter. Body, UI, captions. |
| Mono | **JetBrains Mono** | Only for backend SSE event names (e.g. `producer`, `joiner`) — they appear *as* tags in the progress feed, kept monospace to read as code/tag. |

> Decision: **Fraunces + Inter Tight** is the shipped pair (free, on Google
> Fonts). GT Sectra/Söhne are the aspirational pair if licensing is acquired.

### Type scale (modular, ratio 1.25)

| Token | px / rem | Use |
|-------|----------|-----|
| `text-display-xl` | 72 / 4.5 | Hero on landing only |
| `text-display-lg` | 56 / 3.5 | Trip-detail title (desktop) |
| `text-display-md` | 40 / 2.5 | Section opener |
| `text-display-sm` | 32 / 2.0 | Trip-detail title (mobile), report card title |
| `text-title` | 22 / 1.375 | Card titles, modal titles |
| `text-body-lg` | 18 / 1.125 | Long-form body (report card prose) |
| `text-body` | 16 / 1.0 | Default body |
| `text-body-sm` | 14 / 0.875 | Secondary body, captions |
| `text-caption` | 12 / 0.75 | Labels, eyebrow text, metadata |
| `text-micro` | 10.5 / 0.656 | All-caps eyebrow tags (letter-spaced) |

### Treatment rules

- Display serif: tracking `-0.02em`, line-height `1.05`. Never bold (the contrast
  is in the family itself).
- Body grotesque: tracking `0`, line-height `1.55` for prose, `1.4` for UI.
- Eyebrows / status pills: `text-micro`, all-caps, tracking `0.18em`.
- Numerals: tabular for any number that changes (timers, evidence counts,
  progress depth).

---

## 3. Color tokens

A near-monochrome paper palette with **one** accent (oxidized brass) and a
muted semantic ramp. Defined as HSL CSS variables so the existing Tailwind
config stays compatible.

### Neutrals (the whole product is mostly these)

| Token | HSL | Hex | Use |
|-------|-----|-----|-----|
| `--paper` | `36 22% 96%` | `#F4F0E8` | Page background. Warmer than #FFF. |
| `--paper-elevated` | `36 28% 98%` | `#FAF7F0` | Cards on top of paper |
| `--ink` | `220 18% 10%` | `#15181F` | Primary text. *Not* pure black. |
| `--ink-2` | `220 12% 28%` | `#3F454F` | Secondary text |
| `--ink-3` | `220 8% 48%` | `#71767E` | Tertiary text, captions |
| `--rule` | `30 14% 82%` | `#D8D2C5` | Hairline rules, dividers |
| `--rule-strong` | `30 10% 62%` | `#A39C8C` | Strong dividers |

### Accent

| Token | HSL | Hex | Use |
|-------|-----|-----|-----|
| `--brass` | `36 38% 42%` | `#937642` | Single accent: links, focus rings, the dot in the logo, active tab underline. **Never used as a fill on large surfaces.** |
| `--brass-tint` | `36 38% 92%` | `#F0E6D2` | Subtle highlight (active tab background) |

### Semantic — trip status

Status uses a **muted herbarium** palette (think pressed-flower colors), not
the standard green/yellow/red traffic light. This is the most-visible
in-product signal, and we want it to feel composed, not alarmed.

| Token | HSL | Hex | Maps to |
|-------|-----|-----|---------|
| `--status-pending` | `36 16% 60%` | `#A39B86` | `pending` — sand grey |
| `--status-running` | `200 32% 42%` | `#487A8C` | `running` — atlas blue, animated pulse |
| `--status-complete` | `145 22% 36%` | `#487060` | `complete` — moss green |
| `--status-aborted` | `8 38% 40%` | `#8C4A3F` | `aborted` — terracotta (not red) |

Each has a `-tint` variant (same hue, lightness 92%) for backgrounds.

### Per-card semantic (report tabs)

Each report tab gets a single ink swatch that appears as a thin left border
on cards in that tab. Not as a fill.

| Tab | Token | Hex |
|-----|-------|-----|
| Local Gems | `--tab-gem` | `#937642` (brass) |
| Tourist Traps | `--tab-trap` | `#8C4A3F` (terracotta) |
| Together | `--tab-together` | `#487060` (moss) |
| You-only | `--tab-you` | `#487A8C` (atlas) |
| Partner-only | `--tab-partner` | `#6E5A8C` (heather) |
| Disagreement | `--tab-disagree` | `#3F454F` (ink-2) |

### Dark mode

Out of scope for v1 mockups. Tokens are HSL so dark mode is a future
single-file flip; don't design against it now.

---

## 4. Spacing scale

8-px base, but with two extra-generous tokens for editorial whitespace.

| Token | px | Use |
|-------|----|-----|
| `space-0` | 0 | — |
| `space-1` | 4 | Tight intra-component |
| `space-2` | 8 | Default gap |
| `space-3` | 12 | — |
| `space-4` | 16 | — |
| `space-5` | 24 | Card padding (mobile) |
| `space-6` | 32 | Card padding (desktop), section gap |
| `space-7` | 48 | Section gap (mobile) |
| `space-8` | 64 | Section gap (desktop) |
| `space-9` | 96 | Page gutter (desktop) |
| `space-10` | 144 | Hero whitespace |
| `space-11` | 200 | Editorial silence (used 1-2x per page max) |

### Container widths

| Token | px | Use |
|-------|----|-----|
| `container-prose` | 680 | Long-form report card content |
| `container-content` | 1040 | Default page width |
| `container-wide` | 1280 | Trip-detail with side rail |
| `container-edge-to-edge` | 100% | Hero, footer |

### Radii

Almost zero. `--radius-sm: 2px`, `--radius-md: 4px`, `--radius-lg: 8px`.
**No rounded-2xl anywhere.** Pills are the only thing with full radius
(status badges).

---

## 5. Component inventory

Sorted by atom → molecule → organism. Each item lists the screens it appears in.

### Atoms
- **Hairline** — 1px `--rule` divider; the workhorse of the layout. Used everywhere.
- **Eyebrow** — micro all-caps label above a heading.
- **Status pill** — pending/running/complete/aborted; outline + 6px dot.
- **Tag** — monospace event-name tag (only in progress feed).
- **Button** — three variants:
  - `primary`: ink fill, paper text, no radius beyond 2px.
  - `ghost`: ink text, hairline border, transparent fill.
  - `link`: brass underline (offset 4px), no border.
- **Input** — bottom-rule only (no box). Label sits above as eyebrow.
- **Numeral** — tabular figures, used for evidence counts, timers, depth.

### Molecules
- **Field group** — eyebrow + input + helper. Used in login, trip-new, profile.
- **Companion chip** — initial circle + name; deletable. Used in trip-new + companions page.
- **Source row** — hairline-bordered row with: source icon, snippet, lang flag, link.
- **Evidence count** — `12 sources` with tabular numerals; tooltip shows breakdown.
- **Match score** — two small bars (you / partner), labeled.

### Organisms
- **Site header** — logo (`Plus One` set in display serif, with brass dot between words: `Plus·One`), nav links, account avatar. Sticky, paper-elevated, hairline-bottomed.
- **Footer** — 4-column grid, eyebrow column heads, body links, copyright row.
- **Trip card** (history list item) — destination + dates display serif title, 1-line free-text excerpt, status pill, hairline row.
- **Progress feed** — vertical timeline of SSE events (see §7).
- **Report card** — full-width hairline-bordered card; title + eyebrow tab-tag + evidence count + body prose + expand-for-sources accordion.
- **Tab strip** — text-only tabs, brass underline on active, no pill background.
- **Magic-link sent panel** — quiet confirmation; no "Check your email!" with sparkles.

### Page chrome
- **Editorial header band** — every page uses a 96px (desktop) / 48px (mobile) top band with eyebrow + display title + 1-2-line dek (subhead in body-lg italic). This is the single most-recognizable structural element.

---

## 6. Motion principles

**Rule of thumb:** if a designer at Cereal would consider it tasteful, ship it.
Otherwise cut it.

- **Default easing**: `cubic-bezier(0.2, 0.7, 0.2, 1)` (custom — soft start, decisive arrival).
- **Default duration**: 280ms for state, 480ms for layout, 720ms for hero entrances.
- **Page entry**: hero text staggered fade-up (16px translate, 80ms stagger, max 5 elements).
- **Hairline reveal**: rules draw in left-to-right with `clip-path` over 600ms on first paint. (Used once per page, on the editorial header band.)
- **Hover**: links — underline thickness goes 1px → 1.5px in 180ms; *no* color change.
- **Tab change**: brass underline slides via `transform: translateX`, not width animation.
- **Status `running`**: 1.6s ease-in-out opacity pulse from 1 → 0.55 → 1 on the dot only.
- **NOT allowed**: spring bounces, scale-on-hover for cards, parallax, full-bleed video, confetti, "magic" sparkles, gradient sweeps that travel across the screen.

### Reduced motion

`@media (prefers-reduced-motion: reduce)` disables all of the above except
the status-running pulse, which steps to a 2-state opacity flip every 1.6s.

---

## 7. SSE progress-feed visual language

The progress feed is the **second-most distinctive surface** in the product
(after the editorial header band). Treat it as a visual signature.

### Layout

A vertical line at `space-5` from the left edge. Each event is a row anchored
to that line by a small marker.

```
│
●   PRODUCER · depth 1                           00:04
│   Generating candidates from
│   r/JapanTravel + xhs:tokyo:ramen
│
○   JOINER · depth 1                             00:11
│   Cross-validating evidence
│   12 candidates → 7 with ≥2 sources
│
●   CONTROLLER · depth 1                         00:18
│   Deciding next step
│   ↪ Continue: need disagreement signals
│
```

### Marker rules
- `●` filled = the event has settled (data received).
- `○` hollow = an in-flight event (we've seen the SSE event but UI is still rendering child detail).
- `◆` diamond = `cycle_aborted` (terracotta).
- `■` square = `trip_complete` (moss).

### Color rules
- The **vertical line** is `--rule`.
- The **marker** matches `--status-*` for the cycle-level event; for sub-events (`producer`, `joiner`, `controller`) it's `--ink-2`.
- The **event name** is monospace `text-caption` all-caps tag, ink-2.
- The **depth indicator** is the same tag, with `· depth N` appended.
- The **timer** is tabular numerals, ink-3, right-aligned in the row.
- The **body text** is body-sm, ink-2.

### Event-name → label map

The backend emits machine names; the UI shows English copy *and* the raw tag.

| Event | Tag (mono) | Label (body) |
|-------|------------|--------------|
| `started` | `STARTED` | *(no label — used as the entry marker)* |
| `iteration_start` | `ITER N` | (just bumps depth indicator on subsequent events) |
| `producer` | `PRODUCER · depth N` | "Generating candidates from {sources}" |
| `joiner` | `JOINER · depth N` | "Cross-validating evidence — {n_in} → {n_out}" |
| `controller` | `CONTROLLER · depth N` | "Deciding next step" + reasoning quote |
| `cycle_complete` | `CYCLE COMPLETE` | "Reading complete." |
| `cycle_aborted` | `CYCLE ABORTED` | reason from `data.reason` |
| `trip_complete` | `TRIP COMPLETE` | "Report ready below." (anchor link to report) |

### Live state animation
- New row enters with a 240ms fade + 8px translate-up.
- The vertical line **extends downward** with the new row (animated `height`, 240ms).
- When `trip_complete` arrives, the entire feed fades to 60% opacity and a
  brass hairline appears below it; the report renders below that hairline.

---

## 8. Page wireframes (text)

Each page below has desktop (≥1024) and mobile (<640) variants. Tablet
(640-1024) collapses gracefully — not separately specified.

### 8.1 `/login`

```
DESKTOP
┌───────────────────────────────────────────────────────────┐
│  PLUS·ONE                                  Sign in        │ ← header (hairline below)
├───────────────────────────────────────────────────────────┤
│                                                           │
│              [editorial header band]                      │
│              ── A QUIET ARRIVAL ──                        │
│              Plus One                                     │  ← display-xl
│              Travel with another perspective.             │  ← dek, body-lg italic
│                                                           │
│              ─────────── (hairline, draws in) ─────────── │
│                                                           │
│                                                           │
│                YOUR EMAIL                                 │  ← eyebrow
│                ─────────────────────────                  │  ← bottom-rule input
│                                                           │
│                       [ Send link → ]                     │  ← primary button
│                                                           │
│                We'll send a one-time link.                │  ← helper, ink-3
│                                                           │
└───────────────────────────────────────────────────────────┘

MOBILE
┌─────────────────┐
│ PLUS·ONE        │
├─────────────────┤
│ A QUIET ARRIVAL │
│ Plus One        │
│ Travel with     │
│ another         │
│ perspective.    │
│                 │
│ ─────────────── │
│                 │
│ YOUR EMAIL      │
│ ─────────────── │
│                 │
│ [Send link → ]  │
└─────────────────┘
```

### 8.2 `/auth/exchange`

A *waiting* page. Unlike most auth pages, this one is contemplative.

```
              ── ARRIVING ──
              Letting you in.

              ●  Magic link verified
              ○  Loading your trips
              │
              [hairline]

              You will be redirected.
```

If exchange fails: the eyebrow flips to `── A FRAYED LINK ──` and the body
becomes a quiet explanation + "Send a new link" link button. No red error
banner.

### 8.3 `/trips/new`

Two-column on desktop (form left, brief right), single-column on mobile.

```
DESKTOP
┌───────────────────────────────────────────────────────────┐
│ PLUS·ONE                          Trips · Companions · me │
├───────────────────────────────────────────────────────────┤
│  ── A NEW READING ──                                      │
│  Where will you go?                                       │  ← display-lg
│  Tell me a destination and what kind of trip you want.    │  ← dek
│  ─────────────────────── (hairline) ──────────────────────│
│                                                           │
│  ┌─────────────────────────────┐   ┌────────────────────┐ │
│  │ DESTINATION                 │   │ ── ABOUT ──        │ │
│  │ ──────────────────────      │   │ Plus One reads     │ │
│  │ Tokyo                       │   │ Reddit and         │ │
│  │                             │   │ Xiaohongshu in     │ │
│  │ COMPANIONS  + Add           │   │ both languages,    │ │
│  │ ◐ Yuna   ◑ Wei   ✕          │   │ surfaces what      │ │
│  │                             │   │ locals say, and    │ │
│  │ WHAT MATTERS                │   │ flags where the    │ │
│  │ ┌─────────────────────────┐ │   │ two communities    │ │
│  │ │ tonkotsu ramen,         │ │   │ disagree.          │ │
│  │ │ no tourist traps,       │ │   │                    │ │
│  │ │ vegetarian-friendly     │ │   │ ~90 seconds.       │ │
│  │ └─────────────────────────┘ │   └────────────────────┘ │
│  │                             │                          │
│  │       [ Begin reading → ]   │                          │
│  └─────────────────────────────┘                          │
└───────────────────────────────────────────────────────────┘

MOBILE — same flow, single column, brief becomes a small caption above the form.
```

### 8.4 `/trips/[id]`

The most complex screen. Two phases:

**Phase A — running**: editorial header band on top, full-width progress
feed below. No tabs yet.

```
┌─────────────────────────────────────────────────────────┐
│  ── READING TOKYO ──                                    │
│  Tokyo · for Yuna and Wei                               │ ← display-lg
│  Started 14:02. Status: ● running                       │
│  ─────────────────────── (hairline) ─────────────────── │
│                                                         │
│  │                                                      │
│  ●   STARTED                                  00:00     │
│  │                                                      │
│  ●   PRODUCER · depth 1                       00:04     │
│  │   Generating candidates from               (...)     │
│  │                                                      │
│  ○   JOINER · depth 1                         00:11     │
│  │                                                      │
└─────────────────────────────────────────────────────────┘
```

**Phase B — complete**: the progress feed fades to 60%, a brass hairline
appears, the report tabs render below.

```
[progress feed at 60% opacity]
─── (brass hairline, 600ms reveal) ───

┌─────────────────────────────────────────────────────────┐
│  TL;DR                                                  │ ← eyebrow
│  Tokyo for two, leaning vegetarian, hates tourist       │
│  pricing, loves quiet ramen counters. (display-md)      │
│                                                         │
│  ┌──────────────────────────────────────────────────┐   │
│  │ Together · You-only · Partner-only · Disagreement│   │
│  │ Local Gems · Tourist Traps                       │   │
│  │ ─────────────                                    │   │ ← brass underline on active tab
│  └──────────────────────────────────────────────────┘   │
│                                                         │
│  │ Local Gem                                            │ ← thin brass left border
│  │ ── A COUNTER FOR FOUR ──                             │
│  │ Menya Saimi                                          │ ← display-sm
│  │ Sugamo · 12 sources · matches you 0.91 · partner 0.78│
│  │                                                      │
│  │ Quiet shio counter, no English menu. Locals (jp)     │ ← body-lg prose
│  │ describe a "thin, almost transparent" broth; en      │
│  │ sources rate it lower for novelty but higher for     │
│  │ value. ↓ See sources                                 │
│  │                                                      │
└─────────────────────────────────────────────────────────┘
```

If `cycle_aborted`: the editorial band keeps the title but the status flips
to `● aborted` (terracotta). Below the feed, instead of a brass hairline +
report, render a single quiet card: "We couldn't complete this reading.
{reason}" with a `Try again` ghost button. **No "Oops!" copy. No alarm.**

### 8.5 `/profile`

Dense form, but presented as an editorial table — eyebrow column on the
left, value column on the right, hairline between rows.

```
┌─────────────────────────────────────────────────────────┐
│  ── ABOUT YOU ──                                        │
│  Your reading profile.                                  │
│  ───────────────────────                                │
│                                                         │
│  EMAIL                you@example.com                   │
│  ─────────────────────────────────────────              │
│  AGE RANGE            30 – 45                  ▾        │
│  ─────────────────────────────────────────              │
│  LANGUAGE             English                  ▾        │
│  ─────────────────────────────────────────              │
│  PACE                 Slow ◐── Medium ──○── Fast        │
│  ─────────────────────────────────────────              │
│  LOVES                ramen counters · used books · jazz│  ← chip row
│                                                         │
│  HATES                queues longer than 30m · pricing  │
│                       gimmicks · cruises                │
│  ─────────────────────────────────────────              │
│                                                         │
│                                          [ Save → ]     │
└─────────────────────────────────────────────────────────┘
```

### 8.6 `/companions`

A *contact-book* layout. Each companion is a row, hairline-divided, with
expand-to-edit.

```
┌─────────────────────────────────────────────────────────┐
│  ── WHO YOU TRAVEL WITH ──                              │
│  Companions.                                            │
│  + Add a companion                                      │
│  ───────────────────────                                │
│                                                         │
│  YUNA                          partner · vegetarian     │
│  Loves: kissaten, used books · Hates: smoking sections  │
│  ─────────────────────────────────────────              │
│  WEI                           friend · no constraints  │
│  Loves: izakaya, jazz · Hates: queues                   │
│  ─────────────────────────────────────────              │
└─────────────────────────────────────────────────────────┘
```

### 8.7 `/trips` (history)

A reading list. Reverse-chronological, hairline-divided, no thumbnails.

```
┌─────────────────────────────────────────────────────────┐
│  ── YOUR READINGS ──                                    │
│  Trips.                                                 │
│  ───────────────────────                                │
│                                                         │
│  TOKYO                                                  │
│  for Yuna and Wei · 12 May 2026                         │
│  "tonkotsu ramen, no tourist traps…"                    │
│  ● complete · 22 sources                                │
│  ─────────────────────────────────────────              │
│  KYOTO                                                  │
│  for Yuna · 4 March 2026                                │
│  "temples but quiet ones, kissaten…"                    │
│  ● complete · 18 sources                                │
│  ─────────────────────────────────────────              │
│  OSAKA                                                  │
│  solo · 21 January 2026                                 │
│  "okonomiyaki, deep dive…"                              │
│  ● aborted · Maestro unavailable                        │
│  ─────────────────────────────────────────              │
└─────────────────────────────────────────────────────────┘
```

---

## 9. Accessibility

- All ink/paper combinations exceed WCAG AA (ink on paper = 14.6:1).
- Brass on paper is **3.4:1** — used only for non-essential decoration
  (logo dot, active tab underline). Never used for body text or essential
  controls. Links use brass *underline* but the text itself is ink.
- Focus ring: 2px brass outline at 2px offset on all interactive elements.
- Reduced motion: see §6.
- Status conveyed by **dot shape + label**, not color alone (filled `●`,
  hollow `○`, diamond `◆`, square `■`).

---

## 10. Implementation handoff

For frontend-expert (Tailwind v3 / v4 either way):

```css
:root {
  /* paper */
  --paper:           36 22% 96%;
  --paper-elevated:  36 28% 98%;
  /* ink */
  --ink:             220 18% 10%;
  --ink-2:           220 12% 28%;
  --ink-3:           220 8%  48%;
  /* rule */
  --rule:            30 14% 82%;
  --rule-strong:     30 10% 62%;
  /* brass */
  --brass:           36 38% 42%;
  --brass-tint:      36 38% 92%;
  /* status */
  --status-pending:  36 16% 60%;
  --status-running:  200 32% 42%;
  --status-complete: 145 22% 36%;
  --status-aborted:  8 38% 40%;
  /* shape */
  --radius-sm: 2px;
  --radius-md: 4px;
  --radius-lg: 8px;
  /* motion */
  --ease: cubic-bezier(0.2, 0.7, 0.2, 1);
}
```

Tailwind theme.extend keys to add: `colors.paper`, `colors.ink`,
`colors.rule`, `colors.brass`, `colors.status.*`, `fontFamily.display`,
`fontFamily.body`, `fontFamily.mono`, `fontSize.display-*`, `fontSize.eyebrow`,
`spacing.editorial-{7,8,9,10,11}`.

Fonts via `next/font/google`: Fraunces (display, opsz: 144) and Inter Tight
(body). JetBrains Mono only on the trip-detail page (lazy-loaded).
