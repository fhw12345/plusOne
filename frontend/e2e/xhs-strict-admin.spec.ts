import { expect, test, type APIRequestContext, type Page } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

type AuthUser = { id: string; email: string; username: string; is_admin: boolean };
type LoginResponse = { access_token: string; user: AuthUser };
type LogEntry = { message?: string; source?: string; level?: string; logger?: string };
type WindowWithXhsStrictLogs = Window & {
  __xhsStrictLogs?: string[];
  __xhsStrictLogSource?: EventSource;
};
type Evidence = { source?: string; url?: string; snippet?: string };
type ReportItem = {
  classification?: string;
  evidence?: Evidence[];
  image_url?: string | null;
};
type TripDetail = {
  status?: string;
  content?: { items?: ReportItem[] } | null;
};

const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

test.describe("strict XHS real chain (admin)", () => {
  test.setTimeout(600_000);

  test("admin trip uses cookie Playwright XHS evidence without XHS fallback", async ({
    page,
    request,
  }) => {
    const admin = readAdminCredentials();
    const login = await loginAdmin(request, admin.identifier, admin.password);
    expect(login.user.is_admin, "strict run must use admin credentials").toBe(true);

    await seedBrowserSession(page, login);

    await page.goto("/app/trips/new");
    await page.getByLabel(/the place|destination/i).fill("Tokyo");
    await page
      .getByLabel(/the mood|foods|avoid/i)
      .fill("ramen local gems tourist traps xhs photos no clarifying needed");
    await page.getByRole("button", { name: /go look|plan|start|create/i }).click();

    const clarifier = page.getByTestId("clarifier-step");
    try {
      await expect(clarifier).toBeVisible({ timeout: 8_000 });
      await page.getByRole("button", { name: /skip these/i }).click();
    } catch {
      await expect(clarifier).toBeHidden({ timeout: 1_000 });
    }

    await expect(page).toHaveURL(/\/app\/trips\/[0-9a-f-]{36}/i, { timeout: 10_000 });
    await expect(page.getByTestId("progress-feed")).toContainText(
      /started|producer|joiner|controller|setting up|asking around|cross-check|tying/i,
      { timeout: 30_000 },
    );
    await expect(page.locator("[data-trip-status='complete']")).toBeVisible({
      timeout: 420_000,
    });
    const logMessages = await readAdminLogMessages(page, login.access_token);

    const tripId = page.url().match(/\/app\/trips\/([0-9a-f-]{36})/i)?.[1];
    expect(tripId, "trip id must be present in the URL").toBeTruthy();

    const detailResponse = await request.get(`${apiBase}/api/trips/${tripId}`, {
      headers: { Authorization: `Bearer ${login.access_token}` },
    });
    expect(detailResponse.status(), "trip detail API must respond after completion").toBe(200);
    const detail = (await detailResponse.json()) as TripDetail;
    expect(detail.status).toBe("complete");

    const items = detail.content?.items ?? [];
    expect(items.length, "completed trip must persist report items").toBeGreaterThan(0);
    const xhsEvidence = items.flatMap((item) => item.evidence ?? []).filter(
      (ev) => ev.source === "xiaohongshu",
    );
    expect(xhsEvidence.length, "report must include XHS evidence").toBeGreaterThan(0);
    expect(
      xhsEvidence.every((ev) => ev.url?.includes("xiaohongshu.com/explore/")),
      "XHS evidence must include real note URLs",
    ).toBe(true);
    expect(
      items.some((item) => item.classification !== "insufficient"),
      "strict run must not pass on all-insufficient cards",
    ).toBe(true);
    expect(
      items.some((item) => item.image_url?.startsWith("/media/xhs/")),
      "strict run must persist at least one locally cached XHS image into trip detail image_url",
    ).toBe(true);

    expect(logMessages).toContain("xhs_tier1_scrape_ok");
    expect(logMessages, "XHS strict run must not use fallback logs").not.toMatch(
      /xhs_search_index_hit|xhs_degraded_to_fixture|xhs_total_failure|xhs_tier1_skipped_no_cookie/,
    );
  });
});

async function loginAdmin(
  request: APIRequestContext,
  identifier: string,
  password: string,
): Promise<LoginResponse> {
  const response = await request.post(`${apiBase}/api/auth/login`, {
    data: { identifier, password },
  });
  expect(response.status(), "admin login must succeed").toBe(200);
  const body = (await response.json()) as LoginResponse;
  expect(body.access_token, "admin login must mint a token").toBeTruthy();
  return body;
}

async function seedBrowserSession(page: Page, login: LoginResponse): Promise<void> {
  await page.goto("/");
  await page.evaluate(
    ({ token, user }: { token: string; user: AuthUser }) => {
      window.localStorage.setItem(
        "plus-one-auth",
        JSON.stringify({ state: { token, user }, version: 0 }),
      );
    },
    { token: login.access_token, user: login.user },
  );
  await page.goto("/app");
  await expect(page).toHaveURL(/\/app(\/|$)/);
}

function readAdminCredentials(): { identifier: string; password: string } {
  const env = readBackendEnv();
  const identifier = env.ADMIN_USERNAME || "admin";
  const password = env.ADMIN_PASSWORD || "admin";
  expect(identifier, "ADMIN_USERNAME must be configured").toBeTruthy();
  expect(password, "ADMIN_PASSWORD must be configured").toBeTruthy();
  return { identifier, password };
}

function readBackendEnv(): Record<string, string> {
  const envPath = path.resolve(__dirname, "../../backend/.env");
  if (!fs.existsSync(envPath)) return {};
  const raw = fs.readFileSync(envPath, "utf8");
  const out: Record<string, string> = {};
  for (const line of raw.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    const idx = trimmed.indexOf("=");
    if (idx < 0) continue;
    const key = trimmed.slice(0, idx).trim();
    let value = trimmed.slice(idx + 1).trim();
    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }
    out[key] = value;
  }
  return out;
}

async function readAdminLogMessages(page: Page, token: string): Promise<string> {
  const probe = await startAdminLogProbe(page, token);
  try {
    await expect.poll(() => probe.messages(), { timeout: 10_000 }).not.toBe("");
    return await probe.messages();
  } finally {
    await probe.close();
  }
}

async function startAdminLogProbe(
  page: Page,
  token: string,
): Promise<{ messages: () => Promise<string>; close: () => Promise<void> }> {
  await page.evaluate(
    ({ url }) => {
      const target = window as WindowWithXhsStrictLogs;
      target.__xhsStrictLogs = [];
      target.__xhsStrictLogSource?.close();
      const source = new EventSource(url);
      target.__xhsStrictLogSource = source;
      source.addEventListener("log", (event) => {
        try {
          const entry = JSON.parse((event as MessageEvent<string>).data) as LogEntry;
          target.__xhsStrictLogs?.push(entry.message ?? "");
        } catch {
          // Ignore malformed SSE frames; the probe only cares about log text.
        }
      });
      source.onerror = () => {
        target.__xhsStrictLogs?.push("__admin_log_stream_error__");
      };
    },
    {
      url: `${apiBase}/api/admin/logs/stream?access_token=${encodeURIComponent(token)}`,
    },
  );

  return {
    messages: async () =>
      page.evaluate(() => {
        const target = window as WindowWithXhsStrictLogs;
        return (target.__xhsStrictLogs ?? []).join("\n");
      }),
    close: async () => {
      await page.evaluate(() => {
        const target = window as WindowWithXhsStrictLogs;
        target.__xhsStrictLogSource?.close();
      });
    },
  };
}
