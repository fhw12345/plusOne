import { defineConfig, devices } from "@playwright/test";

const isCI = !!process.env.CI;
const allBrowsers = !!process.env.PLAYWRIGHT_ALL_BROWSERS;

// Backend port: defaults to 8000 (the contract). Local dev can override via
// PLUS_ONE_BACKEND_PORT when port 8000 is already taken by another service.
const backendPort = process.env.PLUS_ONE_BACKEND_PORT ?? "8000";
const apiUrl = process.env.PLAYWRIGHT_API_URL ?? `http://localhost:${backendPort}`;
const backendCommand =
  process.env.PLAYWRIGHT_BACKEND_COMMAND ??
  (process.platform === "win32"
    ? `.\\.venv\\Scripts\\python.exe -m uvicorn plus_one.main:app --host 127.0.0.1 --port ${backendPort}`
    : `uv run uvicorn plus_one.main:app --host 127.0.0.1 --port ${backendPort}`);

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
      // Local Windows dev uses the checked-in venv; CI can override with
      // PLAYWRIGHT_BACKEND_COMMAND. Health probe at
      // /health gives Playwright a real ready signal instead of a port-open
      // false positive.
      command: backendCommand,
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
        // E2E keeps the real LLM code path enabled. By default it points
        // at the local Agent Maestro instance;
        // set MAESTRO_BASE_URL in the parent shell to run against a real
        // Agent Maestro instance instead.
        PLUS_ONE_ALLOW_REAL_LLM: "1",
        MAESTRO_BASE_URL:
          process.env.MAESTRO_BASE_URL ?? "http://127.0.0.1:23333/api/anthropic",
        MAESTRO_AUTH_TOKEN: process.env.MAESTRO_AUTH_TOKEN ?? "Powered by Agent Maestro",
        LLM_DEFAULT_MAX_TOKENS: process.env.LLM_DEFAULT_MAX_TOKENS ?? "16000",
        PLUS_ONE_TOOLS_MODE: process.env.PLUS_ONE_TOOLS_MODE ?? "real",
        PLUS_ONE_TRANSLATE_ENABLED: process.env.PLUS_ONE_TRANSLATE_ENABLED ?? "1",
        PLUS_ONE_TRANSLATE_TIMEOUT_S: process.env.PLUS_ONE_TRANSLATE_TIMEOUT_S ?? "8",
        PLUS_ONE_JOINER_LLM_TIMEOUT_S: process.env.PLUS_ONE_JOINER_LLM_TIMEOUT_S ?? "25",
        XHS_TIMEOUT_S: process.env.XHS_TIMEOUT_S ?? "8",
        NO_PROXY: process.env.NO_PROXY ?? "*",
      },
    },
  ],
});
