import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  clarifyTrip,
  createShare,
  createTrip,
  deleteTrip,
  getSharedTrip,
  getTrip,
  listTrips,
  revokeShare,
  skipClarify,
} from "@/lib/api/trips";
import { ApiError } from "@/lib/api/client";
import { useAuthStore } from "@/store/auth";

const originalFetch = globalThis.fetch;

describe("createTrip", () => {
  beforeEach(() => {
    useAuthStore.setState({ token: "jwt", user: { id: "u1", email: "a@b.test", username: "u", is_admin: false } });
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    vi.restoreAllMocks();
    useAuthStore.setState({ token: null, user: null });
  });

  it("POSTs JSON body and parses the response", async () => {
    const spy = vi.fn(
      async (_input: Parameters<typeof fetch>[0], _init?: Parameters<typeof fetch>[1]) =>
        new Response(
          JSON.stringify({
            trip_id: "11111111-2222-4333-8444-555555555555",
            status: "pending",
          }),
          { status: 202, headers: { "Content-Type": "application/json" } },
        ),
    );
    globalThis.fetch = spy as unknown as typeof fetch;

    const result = await createTrip({ destination: "Tokyo", free_text: "ramen" });

    expect(result.trip_id).toBe("11111111-2222-4333-8444-555555555555");
    const call = spy.mock.calls[0];
    expect(call).toBeDefined();
    const init = (call?.[1] ?? {}) as RequestInit;
    expect(init.method).toBe("POST");
    expect(init.body).toBe(JSON.stringify({ destination: "Tokyo", free_text: "ramen" }));
  });

  it("rejects an invalid response shape", async () => {
    globalThis.fetch = vi.fn(
      async () =>
        new Response(JSON.stringify({ trip_id: "not-a-uuid", status: "x" }), { status: 202 }),
    ) as unknown as typeof fetch;

    await expect(createTrip({ destination: "Tokyo" })).rejects.toBeTruthy();
  });
});

describe("getTrip", () => {
  beforeEach(() => {
    useAuthStore.setState({ token: "jwt", user: { id: "u1", email: "a@b.test", username: "u", is_admin: false } });
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    vi.restoreAllMocks();
    useAuthStore.setState({ token: null, user: null });
  });

  it("GETs and parses the trip detail", async () => {
    const spy = vi.fn(
      async (_input: Parameters<typeof fetch>[0], _init?: Parameters<typeof fetch>[1]) =>
        new Response(
          JSON.stringify({
            trip_id: "11111111-2222-4333-8444-555555555555",
            destination: "Tokyo",
            status: "complete",
            latest_report_id: "11111111-2222-4333-8444-666666666666",
            content: { items: [{ name: "shop a" }] },
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
    );
    globalThis.fetch = spy as unknown as typeof fetch;

    const result = await getTrip("11111111-2222-4333-8444-555555555555");

    expect(result.destination).toBe("Tokyo");
    expect(result.status).toBe("complete");
    expect(result.content?.items.length).toBe(1);
    const call = spy.mock.calls[0];
    const url = String((call as unknown as [string])?.[0]);
    expect(url).toContain("/api/trips/11111111-2222-4333-8444-555555555555");
  });
});

describe("listTrips", () => {
  beforeEach(() => {
    useAuthStore.setState({ token: "jwt", user: { id: "u1", email: "a@b.test", username: "u", is_admin: false } });
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    vi.restoreAllMocks();
    useAuthStore.setState({ token: null, user: null });
  });

  const samplePayload = {
    trips: [
      {
        trip_id: "11111111-2222-4333-8444-555555555555",
        destination: "Tokyo",
        status: "complete",
        created_at: "2026-05-20T14:30:00+00:00",
        latest_report_id: "11111111-2222-4333-8444-666666666666",
        has_report: true,
      },
    ],
    next_cursor: "abc",
  };

  it("builds the query string with limit + cursor", async () => {
    const spy = vi.fn(
      async () =>
        new Response(JSON.stringify(samplePayload), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
    );
    globalThis.fetch = spy as unknown as typeof fetch;

    const res = await listTrips({ limit: 10, cursor: "abc" });
    expect(res.trips).toHaveLength(1);
    expect(res.next_cursor).toBe("abc");

    const call = spy.mock.calls[0];
    const url = String((call as unknown as [string])?.[0]);
    expect(url).toContain("limit=10");
    expect(url).toContain("cursor=abc");
  });

  it("omits both params on a bare call", async () => {
    const spy = vi.fn(
      async () => new Response(JSON.stringify({ trips: [], next_cursor: null }), { status: 200 }),
    );
    globalThis.fetch = spy as unknown as typeof fetch;

    await listTrips();
    const url = String((spy.mock.calls[0] as unknown as [string])?.[0]);
    expect(url).not.toContain("limit=");
    expect(url).not.toContain("cursor=");
    expect(url).toMatch(/\/api\/trips$/);
  });

  it("propagates ApiError on non-2xx", async () => {
    globalThis.fetch = vi.fn(
      async () =>
        new Response(JSON.stringify({ detail: "invalid_cursor" }), {
          status: 400,
          headers: { "Content-Type": "application/json" },
        }),
    ) as unknown as typeof fetch;

    await expect(listTrips({ cursor: "bad" })).rejects.toBeInstanceOf(ApiError);
  });

  it("rejects a malformed response (zod parse failure)", async () => {
    globalThis.fetch = vi.fn(
      async () =>
        new Response(JSON.stringify({ trips: [{ destination: 42 }], next_cursor: null }), {
          status: 200,
        }),
    ) as unknown as typeof fetch;

    await expect(listTrips()).rejects.toBeTruthy();
  });
});

// === Share / Delete / Get-shared ==========================================

describe("createShare", () => {
  beforeEach(() => {
    useAuthStore.setState({ token: "jwt", user: { id: "u1", email: "a@b.test", username: "u", is_admin: false } });
  });
  afterEach(() => {
    globalThis.fetch = originalFetch;
    vi.restoreAllMocks();
    useAuthStore.setState({ token: null, user: null });
  });

  it("POSTs to the share endpoint and parses the response", async () => {
    const spy = vi.fn(
      async (_input: Parameters<typeof fetch>[0], _init?: Parameters<typeof fetch>[1]) =>
        new Response(
          JSON.stringify({
            token: "abc-token-very-long-32chars-xyz",
            share_url: "http://localhost:3000/share/abc-token-very-long-32chars-xyz",
            expires_at: "2026-06-19T14:30:00+00:00",
          }),
          { status: 201, headers: { "Content-Type": "application/json" } },
        ),
    );
    globalThis.fetch = spy as unknown as typeof fetch;

    const tripId = "11111111-2222-4333-8444-555555555555";
    const res = await createShare(tripId);
    expect(res.token).toBe("abc-token-very-long-32chars-xyz");
    expect(res.share_url).toContain("/share/");

    const call = spy.mock.calls[0];
    expect(call).toBeDefined();
    const url = String(call?.[0]);
    const init = (call?.[1] ?? {}) as RequestInit;
    expect(url).toContain(`/api/trips/${tripId}/share`);
    expect(init.method).toBe("POST");
  });
});

describe("revokeShare", () => {
  beforeEach(() => {
    useAuthStore.setState({ token: "jwt", user: { id: "u1", email: "a@b.test", username: "u", is_admin: false } });
  });
  afterEach(() => {
    globalThis.fetch = originalFetch;
    vi.restoreAllMocks();
    useAuthStore.setState({ token: null, user: null });
  });

  it("sends DELETE to the share token endpoint", async () => {
    const spy = vi.fn(
      async (_input: Parameters<typeof fetch>[0], _init?: Parameters<typeof fetch>[1]) =>
        new Response(null, { status: 204 }),
    );
    globalThis.fetch = spy as unknown as typeof fetch;

    const tripId = "11111111-2222-4333-8444-555555555555";
    await revokeShare(tripId, "tok123");
    const call = spy.mock.calls[0];
    expect(call).toBeDefined();
    const url = String(call?.[0]);
    const init = (call?.[1] ?? {}) as RequestInit;
    expect(url).toContain(`/api/trips/${tripId}/share/tok123`);
    expect(init.method).toBe("DELETE");
  });
});

describe("deleteTrip", () => {
  beforeEach(() => {
    useAuthStore.setState({ token: "jwt", user: { id: "u1", email: "a@b.test", username: "u", is_admin: false } });
  });
  afterEach(() => {
    globalThis.fetch = originalFetch;
    vi.restoreAllMocks();
    useAuthStore.setState({ token: null, user: null });
  });

  it("sends DELETE to the trip endpoint", async () => {
    const spy = vi.fn(
      async (_input: Parameters<typeof fetch>[0], _init?: Parameters<typeof fetch>[1]) =>
        new Response(null, { status: 204 }),
    );
    globalThis.fetch = spy as unknown as typeof fetch;

    const tripId = "11111111-2222-4333-8444-555555555555";
    await deleteTrip(tripId);
    const call = spy.mock.calls[0];
    expect(call).toBeDefined();
    const url = String(call?.[0]);
    const init = (call?.[1] ?? {}) as RequestInit;
    expect(url).toMatch(/\/api\/trips\/[0-9a-f-]{36}$/i);
    expect(init.method).toBe("DELETE");
  });

  it("surfaces 409 as ApiError so the dialog can branch on it", async () => {
    globalThis.fetch = vi.fn(
      async () =>
        new Response(JSON.stringify({ detail: "trip_running" }), {
          status: 409,
          headers: { "Content-Type": "application/json" },
        }),
    ) as unknown as typeof fetch;

    await expect(deleteTrip("11111111-2222-4333-8444-555555555555")).rejects.toBeInstanceOf(
      ApiError,
    );
  });
});

describe("getSharedTrip", () => {
  afterEach(() => {
    globalThis.fetch = originalFetch;
    vi.restoreAllMocks();
    // Make sure no auth state leaks in — this endpoint must not need it.
    useAuthStore.setState({ token: null, user: null });
  });

  it("does NOT send an Authorization header even when a token is in the store", async () => {
    // Intentionally seed a token to prove the function ignores it.
    useAuthStore.setState({ token: "should-not-be-sent", user: null });

    const spy = vi.fn(
      async (_input: Parameters<typeof fetch>[0], _init?: Parameters<typeof fetch>[1]) =>
        new Response(
          JSON.stringify({
            trip_id: "11111111-2222-4333-8444-555555555555",
            destination: "Tokyo",
            status: "complete",
            content: { items: [] },
            shared: true,
            expires_at: "2026-06-19T14:30:00+00:00",
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
    );
    globalThis.fetch = spy as unknown as typeof fetch;

    const res = await getSharedTrip("public-token");
    expect(res.destination).toBe("Tokyo");
    expect(res.shared).toBe(true);

    const call = spy.mock.calls[0];
    expect(call).toBeDefined();
    const init = (call?.[1] ?? {}) as RequestInit;
    const headers = (init.headers ?? {}) as Record<string, string>;
    expect(headers.Authorization).toBeUndefined();
    expect(headers.authorization).toBeUndefined();
  });

  it("rejects with share_not_found_or_expired on 404", async () => {
    globalThis.fetch = vi.fn(
      async () =>
        new Response(JSON.stringify({ detail: "share_not_found_or_expired" }), { status: 404 }),
    ) as unknown as typeof fetch;

    await expect(getSharedTrip("nope")).rejects.toThrow(/share_not_found_or_expired/);
  });
});

// === Clarifier (batch-2t) =================================================

describe("clarifyTrip", () => {
  beforeEach(() => {
    useAuthStore.setState({
      token: "jwt",
      user: { id: "u1", email: "a@b.test", username: "u", is_admin: false },
    });
  });
  afterEach(() => {
    globalThis.fetch = originalFetch;
    vi.restoreAllMocks();
    useAuthStore.setState({ token: null, user: null });
  });

  it("POSTs answers and parses the response", async () => {
    const spy = vi.fn(
      async (_input: Parameters<typeof fetch>[0], _init?: Parameters<typeof fetch>[1]) =>
        new Response(JSON.stringify({ status: "running" }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
    );
    globalThis.fetch = spy as unknown as typeof fetch;

    const tripId = "11111111-2222-4333-8444-555555555555";
    const res = await clarifyTrip(tripId, [
      { id: "q1", text: "fixed: may 4–7" },
    ]);
    expect(res.status).toBe("running");
    const call = spy.mock.calls[0];
    const url = String(call?.[0]);
    const init = (call?.[1] ?? {}) as RequestInit;
    expect(url).toContain(`/api/trips/${tripId}/clarify`);
    expect(init.method).toBe("POST");
    expect(init.body).toBe(
      JSON.stringify({ answers: [{ id: "q1", text: "fixed: may 4–7" }] }),
    );
  });

  it("surfaces 409 as ApiError so the UI can navigate anyway", async () => {
    globalThis.fetch = vi.fn(
      async () =>
        new Response(JSON.stringify({ detail: "trip_not_clarifying" }), {
          status: 409,
          headers: { "Content-Type": "application/json" },
        }),
    ) as unknown as typeof fetch;
    await expect(
      clarifyTrip("11111111-2222-4333-8444-555555555555", [
        { id: "q1", text: "yes" },
      ]),
    ).rejects.toBeInstanceOf(ApiError);
  });
});

describe("skipClarify", () => {
  beforeEach(() => {
    useAuthStore.setState({
      token: "jwt",
      user: { id: "u1", email: "a@b.test", username: "u", is_admin: false },
    });
  });
  afterEach(() => {
    globalThis.fetch = originalFetch;
    vi.restoreAllMocks();
    useAuthStore.setState({ token: null, user: null });
  });

  it("POSTs to the skip endpoint with no body and parses the response", async () => {
    const spy = vi.fn(
      async (_input: Parameters<typeof fetch>[0], _init?: Parameters<typeof fetch>[1]) =>
        new Response(JSON.stringify({ status: "running" }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
    );
    globalThis.fetch = spy as unknown as typeof fetch;

    const tripId = "11111111-2222-4333-8444-555555555555";
    const res = await skipClarify(tripId);
    expect(res.status).toBe("running");
    const call = spy.mock.calls[0];
    const url = String(call?.[0]);
    const init = (call?.[1] ?? {}) as RequestInit;
    expect(url).toContain(`/api/trips/${tripId}/clarify/skip`);
    expect(init.method).toBe("POST");
    expect(init.body).toBeUndefined();
  });
});

describe("createTrip — batch-2t clarifying response", () => {
  beforeEach(() => {
    useAuthStore.setState({
      token: "jwt",
      user: { id: "u1", email: "a@b.test", username: "u", is_admin: false },
    });
  });
  afterEach(() => {
    globalThis.fetch = originalFetch;
    vi.restoreAllMocks();
    useAuthStore.setState({ token: null, user: null });
  });

  it("parses clarifier_questions when status is clarifying", async () => {
    globalThis.fetch = vi.fn(
      async () =>
        new Response(
          JSON.stringify({
            trip_id: "11111111-2222-4333-8444-555555555555",
            status: "clarifying",
            clarifier_questions: [
              { id: "q1", text: "fixed dates or flexible?" },
              { id: "q2", text: "okay with bus / metro / both?" },
            ],
          }),
          { status: 201, headers: { "Content-Type": "application/json" } },
        ),
    ) as unknown as typeof fetch;

    const res = await createTrip({ destination: "kyoto" });
    expect(res.status).toBe("clarifying");
    expect(res.clarifier_questions).toHaveLength(2);
    expect(res.clarifier_questions?.[0]).toEqual({
      id: "q1",
      text: "fixed dates or flexible?",
    });
  });

  it("defaults clarifier_questions to [] when omitted (backward compat)", async () => {
    globalThis.fetch = vi.fn(
      async () =>
        new Response(
          JSON.stringify({
            trip_id: "11111111-2222-4333-8444-555555555555",
            status: "running",
          }),
          { status: 201, headers: { "Content-Type": "application/json" } },
        ),
    ) as unknown as typeof fetch;

    const res = await createTrip({ destination: "kyoto" });
    expect(res.status).toBe("running");
    expect(res.clarifier_questions).toEqual([]);
  });
});
