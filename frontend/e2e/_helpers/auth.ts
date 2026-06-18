import { expect, type Page, type APIRequestContext } from "@playwright/test";

// Single source of truth for the e2e sign-in sequence used by every spec
// that needs an authed page. Mirrors the new credential flow from
// batch-2m — registration is skipped here; instead we POST directly to
// /api/auth/register from the test harness, then read the verify code via a
// dev-only endpoint, then call /api/auth/verify, then drop the JWT into the
// browser's localStorage so the page hydrates as authed.
//
// Generates a fresh email + username internally — `Date.now()` alone is not
// unique across `playwright.config.ts:18` (`fullyParallel: true`), so a
// base36 suffix kills the collision risk.
export async function signInE2E(
  page: Page,
  request: APIRequestContext,
): Promise<{ email: string; username: string }> {
  const suffix = `${Date.now()}${Math.random().toString(36).slice(2, 8)}`;
  const email = `e2e${suffix}@plusone.test`;
  const username = `e2e${suffix}`.toLowerCase().slice(0, 30);
  const password = "e2epassword1";

  const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

  const reg = await request.post(`${apiBase}/api/auth/register`, {
    data: { username, email, password },
  });
  expect(reg.status(), "register must succeed").toBe(201);

  // Dev-only helper endpoint that returns the most recent verify code for a
  // given email. Backend ships this in batch-2m as the test substitute for
  // SMTP.
  const lastCode = await pollLastCode(request, apiBase, email);
  expect(lastCode.status(), "dev last-code endpoint must respond").toBe(200);
  const { code } = (await lastCode.json()) as { code: string };
  expect(code, "verify code must be non-empty").toBeTruthy();

  const verifyRes = await request.post(`${apiBase}/api/auth/verify`, {
    data: { email, code },
  });
  expect(verifyRes.status(), "verify must succeed").toBe(200);
  const { access_token, user } = (await verifyRes.json()) as {
    access_token: string;
    user: { id: string; email: string; username: string; is_admin: boolean };
  };
  expect(access_token, "verify must mint a token").toBeTruthy();

  // Seed the zustand persist store so the next navigation lands authed.
  await page.goto("/");
  await page.evaluate(
    ({ token, u }: { token: string; u: typeof user }) => {
      window.localStorage.setItem(
        "plus-one-auth",
        JSON.stringify({ state: { token, user: u }, version: 0 }),
      );
    },
    { token: access_token, u: user },
  );
  await page.goto("/app");
  await expect(page).toHaveURL(/\/app(\/|$)/);

  return { email, username };
}

async function pollLastCode(request: APIRequestContext, apiBase: string, email: string) {
  const url = `${apiBase}/api/auth/dev/last-code?email=${encodeURIComponent(email)}`;
  let response = await request.get(url);
  for (let attempt = 0; response.status() === 404 && attempt < 10; attempt += 1) {
    await new Promise((resolve) => setTimeout(resolve, 100));
    response = await request.get(url);
  }
  return response;
}
