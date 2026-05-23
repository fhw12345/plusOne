import { test, expect, type ConsoleMessage } from "@playwright/test";

// Allow-listed console errors that are pre-existing and tracked separately.
// These come from missing favicon/PWA icons and will be removed once the
// icon set lands. Until then, do not fail the e2e on them.
const ALLOWED_CONSOLE_ERROR_PATTERNS: RegExp[] = [
  /favicon\.ico/i,
  /icon-\d+x\d+\.png/i,
  /apple-touch-icon/i,
  /manifest\.json/i,
];

function isAllowedText(text: string): boolean {
  return ALLOWED_CONSOLE_ERROR_PATTERNS.some((re) => re.test(text));
}

function isAllowed(msg: ConsoleMessage): boolean {
  return isAllowedText(msg.text());
}

test.describe("landing page", () => {
  test("renders with correct title, heading, and tagline", async ({ page }) => {
    const unexpectedErrors: string[] = [];

    page.on("console", (msg) => {
      if (msg.type() === "error" && !isAllowed(msg)) {
        unexpectedErrors.push(msg.text());
      }
    });
    // Uncaught page-level errors (e.g. hydration mismatches) should also fail the spec,
    // but route them through the same allow-list so favicon/icon noise doesn't leak in.
    page.on("pageerror", (err) => {
      if (!isAllowedText(err.message)) {
        unexpectedErrors.push(err.message);
      }
    });

    const response = await page.goto("/");
    expect(response?.status(), "GET / should return 200").toBe(200);

    await expect(page).toHaveTitle("Plus One — AI travel planner");
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(/plus one/i);
    await expect(page.getByText(/travel planner|travel notebook/i).first()).toBeVisible();
    await expect(page.getByRole("link", { name: /let me in|sign in/i })).toBeVisible();

    expect(unexpectedErrors, `unexpected console errors:\n${unexpectedErrors.join("\n")}`).toEqual(
      [],
    );
  });
});
