import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { getProfile, updateProfile } from "@/lib/api/profile";
import { ApiError } from "@/lib/api/client";
import { useAuthStore } from "@/store/auth";

const originalFetch = globalThis.fetch;

const EMPTY = {
  demographics: { age_range: null, language: null },
  travel_style: { budget_sensitivity: null, pace: null, comfort: null },
  explicit_preferences: { loves: [], hates: [] },
  visited_cities: [],
};

describe("profile API client", () => {
  beforeEach(() => {
    useAuthStore.setState({ token: "jwt", user: { id: "u1", email: "a@b.test", username: "u", is_admin: false } });
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    vi.restoreAllMocks();
    useAuthStore.setState({ token: null, user: null });
  });

  it("GET parses the empty-default response", async () => {
    globalThis.fetch = vi.fn(
      async () =>
        new Response(JSON.stringify(EMPTY), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
    ) as unknown as typeof fetch;

    const res = await getProfile();
    expect(res.explicit_preferences.loves).toEqual([]);
  });

  it("PUT sends the full body and parses the response", async () => {
    const spy = vi.fn(
      async (_input: Parameters<typeof fetch>[0], _init?: Parameters<typeof fetch>[1]) =>
        new Response(JSON.stringify(EMPTY), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
    );
    globalThis.fetch = spy as unknown as typeof fetch;

    await updateProfile(EMPTY);

    const call = spy.mock.calls[0];
    const init = (call?.[1] ?? {}) as RequestInit;
    expect(init.method).toBe("PUT");
    expect(init.body).toBe(JSON.stringify(EMPTY));
  });

  it("propagates ApiError on 401", async () => {
    globalThis.fetch = vi.fn(
      async () => new Response(JSON.stringify({ detail: "not_authenticated" }), { status: 401 }),
    ) as unknown as typeof fetch;

    await expect(getProfile()).rejects.toBeInstanceOf(ApiError);
  });

  it("propagates ApiError on 422 validation failure", async () => {
    globalThis.fetch = vi.fn(
      async () => new Response(JSON.stringify({ detail: "validation_error" }), { status: 422 }),
    ) as unknown as typeof fetch;

    await expect(updateProfile(EMPTY)).rejects.toBeInstanceOf(ApiError);
  });
});
