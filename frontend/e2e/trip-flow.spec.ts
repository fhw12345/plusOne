import { test, expect } from "@playwright/test";
import { signInE2E } from "./_helpers/auth";

// Batch 2f PR B — full trip happy path.
// Scaffolded as fixme until the trip surface lands. Once the trip form,
// SSE consumer, and report view ship, drop `.fixme` to activate.
//
// Contract source: docs/prds/batch2f-pr-b-trips.md §4.3 + §6 R5 + skills
// fixture (`backend/src/plus_one/skills/ramen_basics.md` — Tokyo is the
// canonical happy-path destination, so this should reach `complete`,
// not `aborted`).
//
// Generous timeouts: SSE event surface within 20s, terminal status within
// 60s — the producer/joiner/controller cycle plus report persistence
// dominates, and CI is slow.

test.describe("trip flow (happy path)", () => {
  test.setTimeout(420_000);

  test("submit trip → live event → terminal status → report visible", async ({ page, request }) => {
    await signInE2E(page, request);

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

    // At least one progress event surfaces in the live feed. The voice.ts
    // bucketing maps backend reasons into scrapbook-voice text; we accept
    // both the literal event names (older renderings) and the human-voice
    // variants the current UI emits (snapped / hit a wall / stuck / etc.).
    await expect(page.getByTestId("progress-feed")).toContainText(
      /started|producer|joiner|controller|cycle aborted|trip complete|setting up|asking around|pulled|cross-check|tying|snapped|hit a wall|stuck|done|notes app/i,
      { timeout: 20_000 },
    );

    await expect(page.locator("[data-trip-status='complete']")).toBeVisible({ timeout: 300_000 });

    await expect(page.getByText(/Tokyo/i).first()).toBeVisible();

    // Batch 3a — with the e2e Maestro-compatible LLM endpoint enabled,
    // the trip should complete into the itinerary surface and render at
    // least one real <img> card instead of only typed placeholders.
    const itinerary = page.getByTestId("itinerary-view");
    await expect(itinerary).toBeVisible({ timeout: 10_000 });
    await expect(itinerary.getByRole("heading", { name: /Day\s+1/i })).toBeVisible();
    await expect(itinerary.locator("article.photo-card img").first()).toBeVisible();
    await expect(itinerary.locator(".scrawl").first()).toBeVisible();
    await expect(itinerary.locator(".verdict").first()).toBeVisible();

    const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
    const tripId = page.url().match(/\/app\/trips\/([0-9a-f-]{36})/i)?.[1];
    expect(tripId, "trip id must be present in the URL").toBeTruthy();
    const token = await page.evaluate(() => {
      const raw = window.localStorage.getItem("plus-one-auth");
      return raw ? JSON.parse(raw).state.token : null;
    });
    const detail = await request.get(`${apiBase}/api/trips/${tripId}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(detail.status(), "trip detail API must respond after UI completion").toBe(200);
    const body = await detail.json();
    const items = body.content?.items ?? [];
    expect(items.length, "completed trip must persist report items").toBeGreaterThan(0);
    expect(
      items.some((item: { classification?: string }) => item.classification !== "insufficient"),
      "real e2e must not pass on all-insufficient fallback cards",
    ).toBeTruthy();
    expect(
      items.some((item: { evidence?: unknown[] }) => (item.evidence ?? []).length > 0),
      "report items must include source evidence",
    ).toBeTruthy();
    expect(
      items.some((item: { image_url?: string | null }) => !!item.image_url),
      "report should include at least one resolved card image",
    ).toBeTruthy();

    // Batch 2i — perspective toggle and disagreement tab render without
    // crashing on the completed report.
    await expect(page.getByTestId("perspective-toggle")).toBeVisible();
    await expect(page.getByRole("tab", { name: /two minds|disagreement/i })).toBeVisible();

    // Batch 2k — output language toggle is present alongside the
    // perspective toggle. Translation is best-effort in real e2e; this
    // assertion is mechanical, not content-based.
    const languageToggle = page.getByTestId("language-toggle");
    await expect(languageToggle).toBeVisible();
    await languageToggle.getByRole("radio", { name: /english/i }).click();
    await expect(languageToggle).toBeVisible();
  });
});
