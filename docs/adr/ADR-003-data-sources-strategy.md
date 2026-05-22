# ADR-003: Data sources strategy

## Status

Accepted (2026-05-13). Superseded in part: see [ADR-007](./ADR-007-reddit-unauthenticated-json.md) for the Reddit clause.

## Context

The product's core differentiation is "Chinese vs English perspectives + cross-source
disagreement detection." This requires real-time access to multiple data sources of
varying reliability and legal posture.

A senior reviewer pushed hard against live Xiaohongshu scraping, recommending a
curated cached corpus instead. The product owner chose to keep live scraping with
multi-tier fallback.

## Decision

| Source | Role | Method | Reliability tier |
|--------|------|--------|------------------|
| Reddit | Primary English voice | PRAW (official API) | Tier 1 — stable |
| Google Places | Factual data (address, hours, price) | Official API | Tier 1 — stable |
| Wikivoyage | Background knowledge | Static, embed in skills | Tier 1 — stable |
| Xiaohongshu | Primary Chinese voice | Playwright + rotating sessions | Tier 3 — hostile |

### Anti-bot strategy for Xiaohongshu (3-level fallback)

```
L1 (default):
  Playwright headless + real account cookies + residential proxy rotation
  Cache every successful fetch to DB indefinitely

L2 (on captcha / 403):
  Auto-switch to backup account + cooldown 30 min
  Notify dev via email if all backup accounts exhausted

L3 (on total failure):
  Serve from cache with staleness warning to user
  Never let user see a hard error — degrade gracefully
```

### Demo-mode override

In demo mode (`DEMO_MODE=true`), all data sources read from `fixtures/`:
- `fixtures/reddit/` — pre-fetched Reddit JSON
- `fixtures/xhs/` — pre-fetched Xiaohongshu JSON
- `fixtures/google/` — pre-fetched Google Places JSON

Used for: interview demos, CI integration tests, frontend dev without API costs.

## Alternatives considered

### Curated cached corpus only (reviewer's recommendation)

- **Pros**: Zero anti-bot risk, no legal exposure, demo never breaks
- **Cons**: Loses freshness (the whole point of XHS is current local intel), kills the "live cross-source" story
- **Why rejected**: Product owner judged freshness as core value; freshness-loss too high a price

### Skip XHS entirely, English-only

- **Pros**: Simplest legal / ops posture
- **Cons**: Kills primary differentiator (Chinese ↔ English perspective)
- **Why rejected**: No XHS = no product

### Third-party XHS data API (if any exist)

- **Pros**: Outsource the anti-bot fight
- **Cons**: 2026 state: most XHS data APIs are themselves scraping, with same legal posture and worse reliability
- **Why rejected**: Doesn't actually solve the problem

## Consequences

### Positive

- Live data when it works = unique freshness signal
- Multi-tier fallback means demos don't die on stage
- Cache-everything policy means each fetch builds long-term value
- Demo-mode toggle unblocks CI / interview reliability concerns

### Negative / Trade-offs

- Maintenance: anti-bot is an ongoing battle, not a one-shot
- Legal: scraping is a gray area; mitigated by self-use disclaimer + no commercial use until source strategy changes
- Cost: residential proxies + multiple accounts = ongoing $20-50/mo
- Complexity: 3-tier fallback is real engineering (vs static corpus = 0 engineering)

### Follow-ups

- [ ] Document scraper account / proxy / cookie management in `infra/scrapers/`
- [ ] Add scraper health monitor (weekly cron → email alert)
- [ ] Draft the XHS "self-use" disclaimer text for README + landing page
- [ ] Pre-build fixture set for demo mode (~50 representative queries)
- [ ] When ready to commercialize: switch XHS to licensed source or curated corpus

## References

- ADR-001 (tech stack)
- Reviewer feedback re: scraping risk
