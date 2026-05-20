# Plus One — Frontend

Next.js app for the Plus One travel planner.

## Local development

```bash
pnpm install
pnpm dev
```

The dev server expects the FastAPI backend at `http://localhost:8000` (the CI contract).

## Backend port override

Port `8000` collides with Token Server Lite on some local setups. Both the Playwright config (`playwright.config.ts:8`) and Next.js read `PLUS_ONE_BACKEND_PORT` / `NEXT_PUBLIC_API_URL`, so when 8000 is taken, run the backend on a free port (e.g. 8001) and export both vars before invoking `pnpm`:

```bash
PLUS_ONE_BACKEND_PORT=8001 NEXT_PUBLIC_API_URL=http://localhost:8001 pnpm build
PLUS_ONE_BACKEND_PORT=8001 NEXT_PUBLIC_API_URL=http://localhost:8001 pnpm exec playwright test --project=chromium
```

CI does not set the override — it relies on the default `8000`. Do not change the defaults in `playwright.config.ts`; the override mechanism is the supported escape hatch.
