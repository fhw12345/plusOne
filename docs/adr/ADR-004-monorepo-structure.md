# ADR-004: Monorepo structure

## Status

Accepted (2026-05-13)

## Context

Plus One has a Python backend and a TypeScript frontend, plus shared docs,
infra config, and (eventually) shared schema definitions. We need to decide
between monorepo (single git repo) and multirepo (separate repos per service).

## Decision

**Monorepo.** Single git repo with the following top-level structure:

```
plus-one/
├── README.md
├── ARCHITECTURE.md
├── .gitignore
├── .github/
│   ├── workflows/
│   │   └── ci.yml              # Single workflow with backend/frontend jobs
│   └── PULL_REQUEST_TEMPLATE.md
├── docs/
│   ├── prd.md
│   ├── adr/                    # Architecture Decision Records
│   └── notes/                  # Working notes, design sketches
├── backend/
│   ├── pyproject.toml
│   ├── ruff.toml
│   ├── mypy.ini
│   ├── pytest.ini
│   ├── alembic.ini
│   ├── src/plus_one/
│   ├── tests/
│   ├── prompts/                # LLM prompts versioned alongside code
│   ├── fixtures/               # Demo-mode cached data
│   └── scripts/                # CLI tools (seed, scrape, eval)
├── frontend/
│   ├── package.json
│   ├── tsconfig.json
│   ├── tailwind.config.ts
│   ├── next.config.mjs
│   ├── app/
│   ├── components/
│   ├── lib/
│   └── public/
├── infra/
│   ├── docker-compose.yml      # Local dev (postgres + redis + langfuse)
│   ├── docker/
│   │   ├── Dockerfile.web
│   │   └── Dockerfile.worker
│   ├── fly.toml                # Fly.io deploy config
│   └── azure/                  # Bicep / scripts for Azure resources
└── justfile                    # Cross-cutting commands (make-style)
```

## Alternatives considered

### Multirepo

- **Pros**: Clear ownership boundaries, independent CI per service, smaller per-repo size
- **Cons**: Cross-repo changes require coordinated PRs; sharing types is awkward; for solo dev, pure overhead
- **Why rejected**: Solo dev gains nothing from boundary enforcement; loses cross-repo PR atomicity

### Backend-only repo (frontend in separate repo)

- **Pros**: Backend changes don't trigger frontend CI
- **Cons**: Type sharing requires publishing packages or manual sync
- **Why rejected**: CI overhead is minimal; type sharing benefit is real

## Consequences

### Positive

- One PR can change both backend and frontend atomically (e.g. new API endpoint + UI consumer)
- Single CI workflow surfaces the whole project's health
- Cross-cutting refactors (renaming an API) are one PR
- Docs and code stay in sync (ADR + impl in same commit)
- Easier for solo dev to navigate

### Negative / Trade-offs

- Repo grows large over time; eventually CI gets slow
- Frontend devs (if hired later) see backend code (and vice versa)
- Tooling per-language must coexist (Python + Node)

### Follow-ups

- [ ] Set up CI to use path filters (skip backend job if only frontend changed)
- [ ] Use `justfile` for cross-cutting commands (`just dev`, `just test`, etc.)
- [ ] Add `CODEOWNERS` if collaborators ever join

## References

- ADR-001 (tech stack)
