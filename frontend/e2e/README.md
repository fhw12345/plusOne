# E2E (Playwright)

Default flow:

```bash
cd frontend
pnpm build
pnpm exec playwright test --project=chromium
```

`playwright.config.ts` spins up two `webServer` entries: the Next.js frontend
on port 3000 and the FastAPI backend on port 8000 (matching CI).

## Local port-8000 conflict

If port 8000 is held by another service on your machine (e.g. Sydney's Token
Server Lite, which serves `/health` 200 and would be silently latched onto by
Playwright's `reuseExistingServer` + health probe), override the backend port
on both `pnpm build` and the test run:

```bash
PLUS_ONE_BACKEND_PORT=8001 NEXT_PUBLIC_API_URL=http://localhost:8001 pnpm build
PLUS_ONE_BACKEND_PORT=8001 NEXT_PUBLIC_API_URL=http://localhost:8001 \
  pnpm exec playwright test --project=chromium
```

Both vars are needed: `playwright.config.ts:8` already wires
`PLUS_ONE_BACKEND_PORT` through to `webServer[1]`, but `NEXT_PUBLIC_*` is
baked at build time, so the frontend bundle must be rebuilt to point at the
matching port.
