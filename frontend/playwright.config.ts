import { defineConfig, devices } from "@playwright/test";

const isCI = !!process.env.CI;
const allBrowsers = !!process.env.PLAYWRIGHT_ALL_BROWSERS;

// Backend port: defaults to 8000 (the contract). Local dev can override via
// PLUS_ONE_BACKEND_PORT when port 8000 is already taken by another service.
const backendPort = process.env.PLUS_ONE_BACKEND_PORT ?? "8000";
const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? `http://localhost:${backendPort}`;

// Propagate to the test-runner process env so the spec at
// `e2e/auth-flow.spec.ts:27` (which reads `process.env.NEXT_PUBLIC_API_URL`)
// hits the same backend that webServer[1] started.
process.env.NEXT_PUBLIC_API_URL = apiUrl;

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: isCI,
  retries: isCI ? 2 : 0,
  workers: isCI ? 2 : undefined,
  reporter: isCI
    ? [["github"], ["html", { open: "never" }]]
    : [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: "http://localhost:3000",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
    // Local-only browsers — opt in via PLAYWRIGHT_ALL_BROWSERS=1
    ...(allBrowsers
      ? [
          { name: "firefox", use: { ...devices["Desktop Firefox"] } },
          { name: "webkit", use: { ...devices["Desktop Safari"] } },
        ]
      : []),
  ],
  webServer: [
    {
      command: "pnpm start",
      url: "http://localhost:3000",
      reuseExistingServer: !isCI,
      timeout: 120_000,
      stdout: "pipe",
      stderr: "pipe",
      env: {
        NEXT_PUBLIC_API_URL: apiUrl,
      },
    },
    {
      // Run the FastAPI backend from the sibling `backend/` directory.
      // `uv run` activates the venv created by `uv sync`. Health probe at
      // /health gives Playwright a real ready signal instead of a port-open
      // false positive.
      command: `uv run uvicorn plus_one.main:app --host 127.0.0.1 --port ${backendPort}`,
      cwd: "../backend",
      url: `http://localhost:${backendPort}/health`,
      reuseExistingServer: !isCI,
      timeout: 120_000,
      stdout: "pipe",
      stderr: "pipe",
      env: {
        APP_ENV: "development",
        ALLOW_CONSOLE_EMAIL_SENDER: "true",
        AUTH_COOKIE_SECURE: "false",
        // Inherit DATABASE_URL / JWT_SECRET from the parent shell when set
        // (e.g. CI passes them); fall back to local-dev defaults otherwise.
        DATABASE_URL:
          process.env.DATABASE_URL ?? "postgresql+asyncpg://plus_one:dev@localhost:5432/plus_one",
        JWT_SECRET: process.env.JWT_SECRET ?? "dummy-for-e2e",
        // forces MaestroProvider construction error → cycle_aborted → SSE
        // emits a terminal event without external deps
        PLUS_ONE_ALLOW_REAL_LLM: "0",
      },
    },
  ],
});
