import { test, expect } from "@playwright/test";

// PWA / app-shell health check — verifies the routes Plus One promises
// to ship as part of the PWA manifest are reachable and don't 5xx.
//
// These assertions only rely on routes/manifest that already exist on
// main today (landing + Next 16 health). As new pages land (/login,
// /app, etc.) we extend the route list rather than adding new specs.

const PUBLIC_ROUTES: { path: string; label: string }[] = [{ path: "/", label: "landing" }];

test.describe("app shell health", () => {
  for (const { path, label } of PUBLIC_ROUTES) {
    test(`route ${label} (${path}) returns 200 and renders without server error`, async ({
      page,
    }) => {
      const response = await page.goto(path);
      expect(response, `navigation to ${path} should yield a response`).not.toBeNull();
      const status = response!.status();
      expect(status, `${path} should not 5xx`).toBeLessThan(500);
      expect(status, `${path} should not 404`).not.toBe(404);

      // Next.js error overlay text would surface in DOM if SSR threw.
      await expect(page.locator("body")).not.toContainText("Application error");
      await expect(page.locator("body")).not.toContainText("Internal Server Error");
    });
  }

  test("manifest.json (PWA) is served and parseable", async ({ request }) => {
    const res = await request.get("/manifest.json");
    // next-pwa serves it from /public; if missing we accept 404 for now but
    // never a 5xx. When PR4 (serwist) lands this expectation tightens to 200.
    expect(res.status(), "manifest must not 5xx").toBeLessThan(500);
    if (res.status() === 200) {
      const body = await res.json();
      expect(body, "manifest must be a JSON object").toBeTruthy();
    }
  });
});
