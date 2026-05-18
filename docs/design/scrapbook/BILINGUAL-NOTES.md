# Plus One — Bilingual pressure-test findings

> Designer: this is the honest report from running the Scrapbook
> system (Direction D) against Chinese content. I built six pages
> (`pages-zh/`), translated the voice corpus (`VOICE-zh.md`), and
> extended the CSS (`scrapbook-zh.css`).
>
> **§0 below is the v2 correction after user pushback. §1–§11 are
> the v1 history, kept as evidence of what was tried — they have
> `> Revised in §0` callouts where superseded.**

---

## 0. LEGIBILITY-FIRST RULE FOR CJK — revised after user feedback

**Owning the v1 miss.** v1 of these pages used Caveat (Latin handwriting)
paired with Ma Shan Zheng (CJK brush handwriting) as the *body and
headline* register on ZH pages. I shipped that with a confident 7/10
and a "residual concern" footnote about brush feel.

The user looked at a full-page screenshot of `trip-detail-complete.html`
and pushed back hard:

> **「切记不要为了花里胡哨把字体弄得不好看清」**
> (Do not sacrifice legibility for flashy decorative effect.)

They were right. The "residual concern" was not residual — it was the
dominant problem. The page showed: body copy small and low-contrast
grey-on-tan, card titles dissolving into paper texture, Ma Shan Zheng
at 16-22px reading as illegible noise. **My v1 claim that the Caveat ×
Ma Shan Zheng pairing worked as body was wrong in practice.**

### Why it fails for CJK but works for Latin

The same handwriting register (Caveat at 22px) reads fine in English
and dissolves in Chinese because:

| Factor | Latin (Caveat) | CJK (Ma Shan Zheng) |
|--------|----------------|----------------------|
| Glyph density | low — 5-7 letters per inch, lots of negative space | high — 3-5 hanzi per inch, every glyph fills a square |
| Stroke variance | low — handwriting variation lives in slant + connector loops | high — each stroke is a separate brush event with thickness modulation |
| Reader redundancy | high — word-shape recognition compensates for individual letter ambiguity | low — every glyph is meaning-bearing, no fall-back to word silhouette |
| Combined with paper grain | grain noise + sparse Latin = still readable | grain noise + dense brush strokes + thickness modulation = visual sludge |

The same body-text experiment in English looks like "a friend wrote in
my notebook" and in Chinese reads as "calligraphy practice sheet that
got rained on." Different failure modes for different scripts. **EN
pages stay as-shipped — Caveat/Kalam body is correct for Latin.**

### The v2 rule — non-negotiable

1. **All body and headline text in ZH uses `Noto Serif SC`** (Noto
   Serif TC for 繁體). Body ≥ 17px, weight 500 minimum. Headlines large
   and visually dominant, weight 700. Ink color near-black
   (`#1a1814`, exposed as `--ink-cjk`) so dark serif body has real
   contrast against the paper.
2. **Handwriting fonts are accent-only in ZH.** The narrow allowlist:
   - `.annot` — red-pen margin marks
   - `.scrawl` — short caption-style scribbles (1-2 lines max; v2 ZH
     resolves this to printed serif too, but kept in the allowlist
     because it's still a "supporting line" semantically)
   - `.margin-note` — marginalia
   - `.signature` — footer flourish
   - `.doodle` — single-character circles, ticks, ★
   - Forbidden: any headline, body paragraph, button label, nav item,
     card title, list item, input placeholder.
3. **`ZCOOL XiaoWei`** stays for the typewriter slot (nav, type
   labels, stamps, crest). Printed-feel, fine at small sizes.
4. **Paper / grain / tape opacity drops on ZH pages.**
   - Tape opacity: capped at `0.55` (was effectively `~0.9`).
   - Paper grain SVG noise: `opacity: 0.04` (was `0.32`).
   - Paper background: `#fbfaf5` (was `hsl(36 36% 87%)` ≈ `#ECE4D2`,
     too tan — killed serif contrast).
   - Vignette: softened from `.18` to `.10` alpha.
5. **Scrapbook character is preserved via LAYOUT, not type.** Off-axis
   card rotation, tape corners, polaroid frames, paper-clip accents,
   stamps, the perforation strip on tickets, the three-hole punch
   graphic, marginalia in handwriting (small), signatures in
   handwriting — all stay. The voice now comes from composition +
   small handwritten annotations, not from making the body itself
   handwritten.

### Updated slot table (replaces v1 §1 mapping)

| Slot | v1 ZH pick | v2 ZH pick | Notes |
|------|------------|------------|-------|
| body voice (default `.hand`, `.body`, `.lede`) | Ma Shan Zheng 22px | **Noto Serif SC 17-18px, wt 500** | wt 500 not 400 — Noto Serif SC at 400 is slightly weak on a textured background |
| display headline (`.hand-xxl`) | Long Cang 92px | **Noto Serif SC clamp(2.4rem, 5.2vw, 3.2rem), wt 700** | tracking +0.01em; -1° rotate kept for character |
| section headline (`.hand-xl`) | Ma Shan Zheng 46px | **Noto Serif SC clamp(1.5rem, 2.6vw, 1.9rem), wt 700** | |
| card title (`.cap`, `.hand-lg`) | Ma Shan Zheng 25px | **Noto Serif SC 19-20px, wt 700** | |
| supporting line (`.scrawl`) | Liu Jian Mao Cao 16px | **Noto Serif SC 17px, wt 500, soft ink** | still feels like a sub-line via color, not via face |
| messages / SSE (`.msg`) | Ma Shan Zheng 21px | **Noto Serif SC 18px, wt 500** | meta line stays in ZCOOL XiaoWei |
| nav / labels / stamps / crest | ZCOOL XiaoWei | **ZCOOL XiaoWei (unchanged)** | printed slab, fine for CJK at small sizes |
| buttons | ZCOOL XiaoWei 14px + `·` prefix | **Noto Serif SC 16px, wt 700** | dropped the dot prefix — button label now legible without help |
| **annotations** (`.annot`, `.margin-note`, `.signature`, `.doodle`) | (same) | **Ma Shan Zheng / Liu Jian Mao Cao / Long Cang** | the only place CJK handwriting survives. Use sparingly — a few per page. |

### Display rotation note

The `.hand-xxl` headline keeps its -1° rotation in v2 — that's
**layout character**, not type character. A printed serif tilted on
the page still reads as "pinned by hand," not "design system." The
"brush vs felt-tip register split" I called out in v1 §7 dissolves
when both languages are printed serif at the headline level; the
voice difference between English and Chinese headlines is now down
to inherent serif personality (Reckless-feel for both), which is
acceptable.

### What this means for the frontend port

- Token list: drop `--font-hand-cjk` / `-alt` / `-disp` from body
  selectors. Keep them defined as variables but apply only via
  `.annot` / `.margin-note` / `.signature` / `.doodle` classes.
- Add `--ink-cjk: #1a1814;` to TOKENS.md.
- Add `--paper-cjk: #fbfaf5;` to TOKENS.md (or change `--paper`
  itself conditionally via `:lang(zh)`).
- The locale-conditional font split from v1 §8 still applies, but
  the *priority* changes: load Noto Serif SC eagerly (it's now
  body-critical); lazy-load Ma Shan Zheng / Liu Jian Mao Cao / Long
  Cang because they're decorative only.
- The mixed-script `unicode-range` trick (v1 §3) is reduced in scope:
  body Latin now stays in Noto Serif SC, so the trick only applies
  inside `.annot` / `.margin-note` / `.signature` where handwriting
  Latin reads as intentional. `.lat` / `.lat-alt` / `.lat-type`
  spans still work as manual overrides for body Latin tokens
  (reddit, tl;dr, etc.) — use sparingly.

### Confidence (v2)

8.5/10 that a native Chinese reader will look at
`trip-detail-complete.html` on a phone at arm's length and read the
body copy without straining. The 1.5 I'm holding back: I have not
seen a native reader do this in person, only my own visual check on
the screenshots in `screenshots-zh-v2/`. If a native reader still
finds something off, it's more likely to be voice/punctuation than
type — VOICE-zh.md is untouched and remains the candidate to retune.

---

## 0.1 v3 hardening — handwriting CJK BANNED from `.annot` / `.margin-note`

**Owning the v2 miss.** v2 §0 declared a "narrow allowlist" for
handwriting CJK that still included `.annot` and `.margin-note` as a
soft rule ("only short fragments, a few per page"). Soft rules with
no enforcement do not survive contact with real content. The user
pulled four strings off `trip-detail.html` and read them back:

> **「面屋彩未在 12 个不同的帖子里出现 / ★ / ↓ / 我在做什么 / → 这些都看不清」**

All four sat inside `.annot` (or `.scratch-h`, a typewriter-uppercase
micro-label that also failed at 11px). The handwriting CJK fallback
rendered them as Liu Jian Mao Cao at small sizes against textured
paper. They were unreadable. Reproducing the v1 mistake one level
down the hierarchy.

### The v3 rule — enforced, not advisory

1. **Marginalia text is printed serif, period.** `:lang(zh) .annot`,
   `:lang(zh) .margin-note`, `:lang(zh) .msg .annot` all compute to
   `var(--font-cjk-serif-sc), serif`, `clamp(15px, 1.05rem, 17px)`,
   `line-height 1.7`, `letter-spacing 0.01em`, `color: var(--ink-cjk)`
   at opacity 1. Rotation capped at ±1.5deg (was up to ±4deg).
2. **Handwriting CJK allowlist tightened to two slots:**
   - `.signature` — footer flourish, ≤ 6 characters
   - `.doodle` — decorative non-text glyphs (single hanzi, brackets)
   - Forbidden everywhere else, including `.annot`, `.margin-note`,
     `.scrawl`, `.scratch-h`, card titles, buttons, body.
3. **Decorative glyphs go in `.glyph` / `.marker` / `.arrow` / `.star`
   spans.** These render in `"Segoe UI Symbol"` at `max(1em, 18px)`,
   full ink, weight 600. Star `★`, arrows `↓ → ←`, and other
   non-CJK symbols must be wrapped — never left bare inside an
   `.annot` where they'd inherit handwriting fallback.
4. **Micro-labels use `.h-card` / `.label`, never `.annot` /
   `.scrawl`.** `.scratch-h` ("我在做什么 — 直播") got a `:lang(zh)`
   override to `var(--font-cjk-serif-sc)` 16px weight 700, no
   uppercase — typewriter uppercase mangles CJK rendering.

### Cascade bug found and fixed

After the rule rewrite, computed-style spot checks still showed
`.annot` content rendering in `Kalam-Latin, "Liu Jian Mao Cao",
cursive`. Root cause: a later v2 selector `:lang(zh) .annot,
.margin-note, .signature, .doodle { font-family: 'Kalam-Latin',
var(--font-hand-cjk-alt); }` was bridging Latin handwriting through
unicode-range and dropping CJK back to Liu Jian Mao Cao. Fix: removed
`.annot` and `.margin-note` from that selector list. The Latin-inside-
CJK bridge now applies only inside `.signature` and `.doodle`, where
handwriting is the intended register.

### Verification

Six screenshots at 1440 and 360 widths saved to `screenshots-zh-v3/`
for `trip-detail.html`, `trip-detail-complete.html`,
`trip-detail-kyoto-mixed.html`. `browser_evaluate(getComputedStyle)`
on each of the four target strings confirms Noto Serif SC,
16-17px, `rgb(26, 24, 20)`, opacity 1. Glyphs in target strings
confirm Segoe UI Symbol, ≥ 18px, full ink.

### Updated slot table delta

| Slot | v2 ZH pick | v3 ZH pick |
|------|------------|------------|
| `.annot` (red-pen margin marks) | Ma Shan Zheng / Liu Jian Mao Cao | **Noto Serif SC `clamp(15,1.05rem,17)` wt 500, ink full** |
| `.margin-note` | (same) | **same as `.annot`, rotation ±1° max** |
| `.scratch-h` (scratchpad heading) | ZCOOL XiaoWei 11px upper | **Noto Serif SC 16px wt 700, no upper** |
| `.glyph` / `.marker` / `.arrow` / `.star` | (did not exist) | **Segoe UI Symbol `max(1em,18px)` wt 600 ink full** |
| `.signature`, `.doodle` | handwriting CJK | **unchanged — the only allowed slots** |

---

## 1. Hand + CJK pairing — Caveat × Noto Serif SC **fails**, Caveat × Ma Shan Zheng **works**

> **Revised in §0.** This section's conclusion ("Caveat × Ma Shan
> Zheng works as body") was wrong in practice. v2 reverts to Noto
> Serif SC for body and headlines. Ma Shan Zheng / Liu Jian Mao Cao
> / Long Cang are scoped to annotations only.

The original spec said "Caveat + Noto Serif SC" for body. After
rendering an actual page I confirm: this pairing does not work as a
*handwriting* register.

- Caveat is **felt-tip handwritten**.
- Noto Serif SC is **printed serif** — a book face, not a hand.
- Side-by-side the English looks like a friend's note and the Chinese
  looks like a textbook. The voice (which is the whole point of D)
  collapses.

The fix in `scrapbook-zh.css`:

| Slot | Pick | Why |
|------|------|-----|
| body voice (hand) | **Ma Shan Zheng** | brush-feel CJK handwriting; pairs with Caveat at the *register* level (both feel made-by-hand) |
| annotations (.scrawl, .annot) | **Liu Jian Mao Cao** | looser, faster CJK script; matches Kalam's "second voice" role |
| display headlines | **Long Cang** (fallback Ma Shan Zheng) | slightly wilder for big titles; sits next to Caveat hand-xxl convincingly |
| typewriter slot (was Special Elite — Latin only) | **ZCOOL XiaoWei** | literary slab CJK; closest analog to Special Elite's "printed by a machine" feel |
| printed-view body | Noto Serif SC | here Noto Serif SC is correct — printed view IS the book register |
| printed-view (TC) | Noto Serif TC | for the one Traditional sample |
| printed-view typewriter | Noto Sans SC | typewriter face in printed view is silly; use sans for nav/labels |

**Reject pile** — what I tried and dropped:
- *Liu Jian Mao Cao for body*: too cursive, illegible at 16-22px next to dense info. Kept only for `.scrawl`/`.annot`.
- *Source Han Sans Light for body*: looks like a magazine, kills the hand-feel.
- *ZCOOL KuaiLe*: too cute (Tumblr-2014 risk that DIRECTION_OPTIONS Part 4 flagged for D).
- *Caveat alone with system CJK fallback*: gives Microsoft YaHei on Windows, which looks like a workplace doc. Hardest no.

**TOKEN UPDATE for frontend-expert:**

```
--font-hand-cjk:      'Ma Shan Zheng', 'Long Cang', 'Caveat', cursive;
--font-hand-cjk-alt:  'Liu Jian Mao Cao', 'Long Cang', 'Kalam', cursive;
--font-hand-cjk-disp: 'Long Cang', 'Ma Shan Zheng', cursive;
--font-cjk-serif-sc:  'Noto Serif SC', 'Source Han Serif SC', serif;
--font-cjk-serif-tc:  'Noto Serif TC', 'Source Han Serif TC', serif;
--font-cjk-type:      'ZCOOL XiaoWei', 'Noto Serif SC', serif;
--font-cjk-sans:      'Noto Sans SC', 'PingFang SC', sans-serif;
```

Add these to `TOKENS.md` and the `@theme` block. The font load
budget grows: from 6 web families (EN) to 11 (EN + CJK). Mitigation
in §8.

---

## 2. Line-height — CJK needs **1.55–1.85**, not 1.32–1.4

The English `.hand` uses `line-height: 1.32`. Set on Chinese, glyphs
visually touch — descenders of one row clip ascenders of the next.
The square CJK glyph shape needs more vertical room than Latin.

Final values shipped:

| Class | EN | ZH |
|-------|------|------|
| `.hand` body | 1.32 | **1.75** |
| `.hand-xxl` display | 0.92 | **1.18** |
| `.scrawl` | 1.45 | **1.75** |
| `.msg` (SSE) | 1.28 | **1.55** |
| `.tldr` | 1.18 | **1.5** |

Recommendation for `TOKENS.md`: add a `--lh-cjk-*` variable family
so the frontend port doesn't have to re-derive these:

```
--lh-cjk-tight: 1.55;
--lh-cjk-body:  1.75;
--lh-cjk-disp:  1.18;
```

---

## 3. Mixed-script kerning — Latin words inside CJK paragraphs

The hardest visual test. Real sentence from `trip-detail-kyoto-mixed.html`:

> 想找京都裡那種 slow morning 的咖啡店

Default behavior: browser picks Ma Shan Zheng for everything, falls
back for Latin glyphs to whatever the system has. Result: `slow
morning` renders in *Microsoft YaHei italic-fallback* on Windows,
which looks like a typing error.

**Fix** (in `scrapbook-zh.css`): a `@font-face` declaration with
`unicode-range` that scopes Caveat to Latin glyph ranges only, then
the font-stack lists `'Caveat-Latin'` *first* on `:lang(zh)`
selectors:

```css
@font-face {
  font-family: 'Caveat-Latin';
  src: local('Caveat'), local('Caveat-Regular');
  unicode-range: U+0020-024F, U+2000-206F, U+20A0-20CF;
  font-display: swap;
}

:lang(zh) .hand { font-family: 'Caveat-Latin', var(--font-hand-cjk); }
```

This gets Caveat for the Latin glyphs and Ma Shan Zheng for the CJK
glyphs *in the same sentence*. Visual result: handwritten English
inside handwritten Chinese, both reading as "made by hand."

**Also added** a manual override class `.lat` (and `.lat-alt`,
`.lat-type`) for cases where the unicode-range trick isn't enough —
e.g., a `<span class="lat">reddit</span>` inside a stamped label. Use
liberally in the HTML. Examples are throughout `pages-zh/`.

---

## 4. Punctuation — half-width inside chat voice, full-width in printed view

A real tension in D specifically: the voice is *casual chat*, where
Chinese speakers routinely mix `,` and `.` (half-width Western
punctuation). The standard `，` `。` (full-width) reads as *formal* /
*official document*, which is exactly the AI-tool register we're
escaping.

Decision shipped:
- **Hand register** (`pages-zh/*.html`): use casual half-width
  punctuation in body copy. Use `「」` for emphasis (sounds "quoted by
  the person speaking"). Skip `、` — it's too formal for SMS voice.
- **Printed view** (the `换成打印体` toggle): switch to full-width
  `，。「」、`. This isn't automatic — the markup itself uses the
  casual punctuation, and the printed-view CSS opts in via
  `text-spacing-trim: trim-start` + `hanging-punctuation: allow-end`
  which optically nudges fullwidth punctuation closer to glyphs.

The CSS supports both. *Markup choice is intentional and per-string*
— no global substitution. See `VOICE-zh.md` for which strings use
which.

---

## 5. Button copy length — Chinese is shorter, buttons look empty

`send the link` (12 chars) → `把链接发过来` (5 hanzi). The English
button at 22px padding looks right; the Chinese button at the same
padding looks like 50% empty space.

**Fix** (`scrapbook-zh.css`):
- Add a leading `·` prefix character (typewriter dot, ink-3 color)
  via `:lang(zh) .btn::before { content: '·'; }`. Visually balances
  the button without changing the text.
- Bump button font-size from 12px to 14px (CJK reads ~2px larger
  than Latin at equivalent perceptual size).
- Reduce letter-spacing 0.22em → 0.1em (already on the typewriter
  slot via ZCOOL XiaoWei).

Same fix for the `换成打印体` view-toggle (5 chars vs 17 in English):
added a `min-width: 130px` floor so the button doesn't shrink to
postage-stamp width.

---

## 6. Stamp / type slots — `text-transform: uppercase` is meaningless in CJK

CJK has no upper/lower case. The English `.type`/`.crest`/`.stamp` all
have `text-transform: uppercase` + `letter-spacing: 0.2em`. With
CJK text:
- `uppercase` is a no-op (no glyphs change).
- 0.2em letter-spacing on already-square CJK glyphs creates a
  *visually broken row* — the eye reads each character as isolated.

**Fix**: on `:lang(zh)` versions of these selectors, set
`text-transform: none` and drop letter-spacing to 0.04em-0.1em range
(varies by component). The typewriter face *itself* (ZCOOL XiaoWei)
carries the "this is a stamped/printed label" register without needing
the typographic shorthand.

For purely Latin stamp content (dates like `12 MAY 2026`, station
codes), the markup keeps Special Elite via `.lat-type` class — best
of both.

---

## 7. The residual concern — **headline display face**

> **Revised in §0.** The "residual" concern in this section turned
> out to be the dominant problem, not a footnote. v2 puts headlines
> in Noto Serif SC; the brush-vs-felt-tip register split dissolves
> when both languages use printed serif at the headline level.

The one place I'm still not fully sold on the pair: the big
`.hand-xxl` headline.

- English: "Tokyo" in Caveat 600 at 96px, rotated -1° — feels like
  someone wrote on the cover of a notebook with a fat marker.
- Chinese: "东京" in Long Cang at 92px, rotated -1° — feels closer
  to *brush calligraphy* than to *fat-marker notebook scrawl*.

These two registers (felt-tip vs brush) are both *handwritten* but
they signal different *contexts*. The Chinese reads more "literary
travelogue," the English reads more "friend's notebook." Not a
failure — different shading of the same direction — but worth
flagging.

**Options if this matters in user testing:**
- A) Accept the slight register split. Brush-feel for Chinese
  headlines is *culturally on-brand* for travel writing; the
  pretence of fat-marker felt-tip in Chinese is the actual
  inauthentic move.
- B) Force a unified register by switching English headlines to
  Reckless or another brush-adjacent serif. Loses some of Caveat's
  warmth; gains pair coherence.
- C) Use the printed-view font (Noto Serif SC + Source Serif 4) on
  headlines only, treat headlines as *printed magazine titles* in
  both languages, keep handwriting for body. This is the editorial-
  hybrid I'd flag as a real candidate if the user pushes back.

My recommendation: A. The Chinese-speaking traveler will not perceive
the brush register as wrong; English-only viewers won't see the
Chinese to compare. We only have a coherence problem if someone
compares the two side-by-side, which only happens in design docs like
this one.

---

## 8. Performance / font load budget

Going from EN-only to bilingual jumps web-font requests substantially:

| State | Families | Approx KB (woff2) |
|-------|----------|--------------------|
| EN only | 6 (Caveat, Kalam, Special Elite, Shippori Mincho, Noto Serif JP, Plus Jakarta Sans) | ~120 KB |
| + ZH | +5 (Ma Shan Zheng, Liu Jian Mao Cao, Long Cang, ZCOOL XiaoWei, Noto Serif SC, Noto Serif TC, Noto Sans SC) | ~+800 KB (CJK is unavoidably heavier) |

**Mitigation for the Next.js port:**
- Use `next/font` with `display: 'swap'` for non-critical faces.
- *Subset* Noto Serif SC + Noto Serif TC to the GB/T 7714 common
  subset (~3500 glyphs) using `pyftsubset` in a build step. Drops
  ~400 KB.
- Load Liu Jian Mao Cao + Long Cang + ZCOOL XiaoWei lazily only when
  `<html lang="zh-*">` is set — split the Google Fonts URL into two
  `@import`s and conditionally include the CJK one via
  `next/font/google` based on the user's locale.
- Cache aggressively — these don't change across releases.

`scrapbook-zh.css` currently does **one** unconditional Google Fonts
request. For prototyping that's fine. The frontend port must do the
locale-conditional split.

---

## 9. Voice translation — what worked, what's awkward

VOICE-zh.md is written *as if by a Chinese designer writing for a
Chinese friend*, not translated from English. The cycle-aborted line
is the proof point:

| English | Chinese |
|---------|---------|
| `hit a wall — couldn't get through to my notes app. give me a sec and try again?` | `撞墙了 — 笔记应用没回我。等一下再试？` |

Both read as casual chat. Both signal: the AI is hidden, this is a
person speaking. Both are the same length on screen.

What still feels slightly off:

- `producer` line 2 (`12 names so far from reddit. saving the ones
  that show up twice.`) → `reddit 这边目前 12 个名字。重复出现的我
  标一下。` The Chinese reads slightly more formal than the English.
  Tried `重复的我标一下` — too clipped. Settled on the longer form.
  *Minor*; would polish in user testing.

- `iteration_start` line 4 (`last pass — pulling the loose threads
  together.`) → `最后一轮，把零碎线索串起来。` The English has a
  *resigned-but-fond* tone ("loose threads"); the Chinese reads more
  *organizational* ("零碎线索"). Couldn't find a less corporate
  match without becoming twee. Acceptable.

- `tl;dr` heading — kept as `tl;dr` (latin token). Translating it
  (`简言之`) reads as a textbook. Real Chinese internet users keep
  `tl;dr` in latin. Same call as `reddit`, `小红书`, `tonkotsu`.

---

## 10. What to copy back to the English files

A few learnings from the CJK side that improve the EN side too:

1. **Use `.lat` / `.lat-alt` / `.lat-type` even in EN files** for
   the rare bilingual mention — e.g., `「<span class="lat-type">PLUS
   · ONE</span> · reading no. 047」` already does this. Make it a
   habit, not an afterthought.

2. **The half-width punctuation decision** is worth documenting in
   the English VOICE.md too. The English voice should also resist
   the corporate hand — `Loading…` is banned, but `Submitting...`
   (with three dots) sneaks in. Add to the banned-phrases list.

3. **Long Cang for English display?** I tested it briefly. No — it
   doesn't have Latin coverage that matches its Chinese character.
   Keep Caveat for English headlines.

---

## 11. Plan B — what to do if the user vetoes the pair

If the user looks at `trip-detail-complete.html` (the most important
page to pass the native-speaker test) and says "this still feels off"
or "the brush feel is wrong for me":

**Plan B-1:** Drop Ma Shan Zheng for body, switch to **Cactus
Classical Serif** (font: 仓耳今楷). It's a more reserved handwriting
face — closer to neat student handwriting than brush. Loses some
warmth, gains universal acceptability.

**Plan B-2:** Go to the editorial-hybrid I flagged in §7 option C —
serif for all headlines (Noto Serif SC + Source Serif 4 in matched
weights), handwriting for body only. Pairs cleanly with Direction E
fallback if the user wants to pivot.

**Plan B-3 (nuclear):** If neither lands, the **brush vs felt-tip
register split is fundamental** and D may not be the right direction
for the bilingual target audience. The recommendation in
DIRECTION_OPTIONS Part 5 acknowledged 7/10 confidence specifically
because of risk of "too cute." If Chinese readers find brush-feel
*too literary* in the same way English readers might find felt-tip
*too cute*, the direction needs revisiting at the brief level, not
the typography level.

I'd want to see this fail in front of an actual Chinese-speaking user
before invoking B-3. B-1 and B-2 are cheap to try first.

---

## Files updated / created

- `docs/design/scrapbook/scrapbook-zh.css` — CJK extensions, loads
  after scrapbook.css, scoped via `:lang(zh)`
- `docs/design/scrapbook/VOICE-zh.md` — full corpus
- `docs/design/scrapbook/pages-zh/` — 6 pages (login, trip-new,
  trip-detail running, trip-detail complete with tabs, profile,
  trip-detail kyoto mixed-language Traditional sample)
- `docs/design/scrapbook/BILINGUAL-NOTES.md` — this document
- `docs/design/scrapbook/index.html` — updated with 中文 section
  (added in same task)

## TODO for frontend-expert (when porting)

1. Add the 4 new CJK font tokens to `TOKENS.md` `@theme` block.
2. Add `--lh-cjk-*` line-height tokens.
3. Implement the locale-conditional font split — don't load CJK
   families on `<html lang="en">` pages.
4. Subset Noto Serif SC/TC in a build step (~400 KB savings).
5. Carry over the `unicode-range` `@font-face` trick for Caveat/Kalam
   *exactly* as written in `scrapbook-zh.css`. Don't refactor it; it's
   load-bearing for the mixed-script kerning.
6. The `.lat` / `.lat-alt` / `.lat-type` classes need to survive into
   the React component layer — make them part of a `<Lat>` component
   so writers don't have to remember the class name.
