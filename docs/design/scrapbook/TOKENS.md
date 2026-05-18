# Plus One — Scrapbook Tokens (Direction D)

Single source of truth for design tokens. Mirrors `:root` in
`scrapbook.css`. When frontend-expert updates STACK_REVIEW.md's
`@theme` block in `app/globals.css`, copy from here.

All colors are HSL components (Tailwind v4 `@theme` consumes them
that way; the css uses `hsl(var(--name))` everywhere).

---

## Color tokens

### Substrate

| Token | HSL | Hex | Usage |
|-------|-----|-----|-------|
| `--paper`   | `36 36% 87%` | `#ECE4D2` | page base — aged notebook |
| `--paper-2` | `42 44% 92%` | `#F5EFE0` | raised scrap (scratchpad, ticket) |
| `--paper-3` | `38 32% 80%` | `#E0D6BC` | sunken scrap (tldr, receipt) |
| `--kraft`   | `36 30% 67%` | `#C9B58E` | binder edge, dotted rules |

### Inks

| Token | HSL | Hex | Usage |
|-------|-----|-----|-------|
| `--ink`    | `32 20% 14%` | `#2A241B` | primary ink |
| `--ink-2`  | `34 17% 27%` | `#4F4538` | secondary copy |
| `--ink-3`  | `36 18% 42%` | `#7C6F58` | captions, meta |
| `--pencil` | `36 20% 46%` | `#8C7B5E` | pencil-grey |

### Action / signal

| Token | HSL | Hex | Usage |
|-------|-----|-----|-------|
| `--red`      | `6 54% 47%`  | `#B94335` | red marker, verdict, live |
| `--red-tape` | `8 47% 73%`  | `#D8A89A` | pale washi tape (red) |
| `--sepia`    | `28 56% 30%` | `#7A4F22` | stamp ink, station codes |

### Washi tape (corner accents only — never fills)

| Token | HSL | Hex |
|-------|-----|-----|
| `--tape-mint`   | `135 24% 79%` | `#BCD4C0` |
| `--tape-blue`   | `210 21% 72%` | `#A8B8C8` |
| `--tape-yellow` | `48 65% 70%`  | `#E8D27A` |

### Status (rendered as colors, never as words)

| Token | HSL | Maps to old name |
|-------|-----|------------------|
| `--signal-live` | `6 54% 47%` | running |
| `--signal-done` | `96 22% 36%` | complete |
| `--signal-wait` | `36 18% 42%` | pending |
| `--signal-snag` | `16 60% 38%` | aborted |

---

## Typography tokens

| Token | Stack | When |
|-------|-------|------|
| `--font-hand`      | `'Caveat', cursive`             | body voice, captions, headlines |
| `--font-hand-alt`  | `'Kalam', cursive`              | annotations, secondary scrawl |
| `--font-type`      | `'Special Elite', monospace`    | stamps, dates, ALL CAPS, station codes |
| `--font-cjk-serif` | `'Shippori Mincho', 'Noto Serif JP', serif` | Japanese place names |
| `--font-print`     | `'Plus Jakarta Sans', sans-serif` | printed-view fallback only |

Google Fonts URL (single request):

```
https://fonts.googleapis.com/css2?
  family=Caveat:wght@400;500;600;700
  &family=Kalam:wght@400;700
  &family=Special+Elite
  &family=Shippori+Mincho:wght@400;500;700
  &family=Noto+Serif+JP:wght@400;500;700
  &family=Plus+Jakarta+Sans:wght@400;500;600
  &display=swap
```

---

## Motion tokens

| Token | Value |
|-------|-------|
| `--ease`      | `cubic-bezier(0.22, 0.61, 0.36, 1)` |
| `--ease-soft` | `cubic-bezier(0.4, 0, 0.2, 1)` |
| `--dur-quick` | `140ms` |
| `--dur`       | `260ms` |
| `--dur-slow`  | `520ms` |

---

## Layout

| Token | Value |
|-------|-------|
| `--shell-max` | `1180px` |
| `--gutter`    | `clamp(20px, 4vw, 36px)` |
| `--r-punch`   | `50%` (only border-radius use — circular hole-punch) |

---

## Tailwind v4 `@theme` block (drop-in for `app/globals.css`)

```css
@import "tailwindcss";

@theme {
  /* substrate */
  --color-paper:    hsl(36 36% 87%);
  --color-paper-2:  hsl(42 44% 92%);
  --color-paper-3:  hsl(38 32% 80%);
  --color-kraft:    hsl(36 30% 67%);

  /* inks */
  --color-ink:      hsl(32 20% 14%);
  --color-ink-2:    hsl(34 17% 27%);
  --color-ink-3:    hsl(36 18% 42%);
  --color-pencil:   hsl(36 20% 46%);

  /* signal */
  --color-red:        hsl(6 54% 47%);
  --color-red-tape:   hsl(8 47% 73%);
  --color-sepia:      hsl(28 56% 30%);
  --color-signal-snag: hsl(16 60% 38%);
  --color-signal-done: hsl(96 22% 36%);

  /* tape */
  --color-tape-mint:   hsl(135 24% 79%);
  --color-tape-blue:   hsl(210 21% 72%);
  --color-tape-yellow: hsl(48 65% 70%);

  /* type */
  --font-hand:     'Caveat', cursive;
  --font-hand-alt: 'Kalam', cursive;
  --font-type:     'Special Elite', monospace;
  --font-cjk:      'Shippori Mincho', 'Noto Serif JP', serif;
  --font-print:    'Plus Jakarta Sans', sans-serif;

  /* radius - only one */
  --radius-punch: 50%;

  /* motion */
  --ease-paper:    cubic-bezier(0.22, 0.61, 0.36, 1);
  --duration-quick: 140ms;
  --duration-base:  260ms;
  --duration-slow:  520ms;
}
```

---

## Notes for the frontend port

- Tilt is per-instance via inline `style="--tilt: -1.7deg"` (a small
  build step or render-time random in [-2.5°, +2.5°] is fine; keep it
  *stable per card-id* so re-renders don't re-tilt).
- The grain SVG (`body::before`) is one inlined SVG filter — no asset.
- Don't introduce a CSS reset beyond what `scrapbook.css` already does;
  Tailwind preflight conflicts with the substrate styles and must be
  scoped/disabled on the trip-detail surface.
- The `.printed-view` class on `<html>` is the a11y opt-out. Toggle
  with localStorage `plusone.view = "printed" | "scrapbook"`. The
  toggle button (`.view-toggle`) is fixed top-right and rendered in
  every layout.
- `prefers-reduced-motion` is honored automatically by the CSS — no
  JS check needed.
