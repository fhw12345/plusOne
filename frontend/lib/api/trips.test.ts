import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { createTrip, getTrip } from "@/lib/api/trips";
import { useAuthStore } from "@/store/auth";

const originalFetch = globalThis.fetch;

describe("createTrip", () => {
  beforeEach(() => {
    useAuthStore.setState({ token: "jwt", user: { id: "u1", email: "a@b.test" } });
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
    useAuthStore.setState({ token: "jwt", user: { id: "u1", email: "a@b.test" } });
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
    const url = String(call?.[0]);
    expect(url).toContain("/api/trips/11111111-2222-4333-8444-555555555555");
  });
});
