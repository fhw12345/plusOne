import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  CompanionConflictError,
  createCompanion,
  deleteCompanion,
  listCompanions,
  updateCompanion,
} from "@/lib/api/companions";
import { ApiError } from "@/lib/api/client";
import { useAuthStore } from "@/store/auth";

const originalFetch = globalThis.fetch;

const COMPANION = {
  id: "11111111-2222-4333-8444-555555555555",
  name: "Anna",
  explicit_preferences: { loves: ["matcha"], hates: [] },
  constraints: { dietary: [], mobility: null, max_walking: null },
  created_at: "2026-05-20T14:30:00+00:00",
  updated_at: "2026-05-20T14:30:00+00:00",
};

const CREATE_BODY = {
  name: "Anna",
  explicit_preferences: { loves: [], hates: [] },
  constraints: { dietary: [], mobility: null, max_walking: null },
};

describe("companions API client", () => {
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

  it("list parses an empty list", async () => {
    globalThis.fetch = vi.fn(
      async () =>
        new Response(JSON.stringify({ companions: [] }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
    ) as unknown as typeof fetch;

    const res = await listCompanions();
    expect(res.companions).toEqual([]);
  });

  it("create POSTs and parses the new companion", async () => {
    const spy = vi.fn(
      async (_input: Parameters<typeof fetch>[0], _init?: Parameters<typeof fetch>[1]) =>
        new Response(JSON.stringify(COMPANION), {
          status: 201,
          headers: { "Content-Type": "application/json" },
        }),
    );
    globalThis.fetch = spy as unknown as typeof fetch;

    const res = await createCompanion(CREATE_BODY);
    expect(res.id).toBe(COMPANION.id);

    const call = spy.mock.calls[0];
    const init = (call?.[1] ?? {}) as RequestInit;
    expect(init.method).toBe("POST");
  });

  it("create surfaces 409 companion_name_taken as CompanionConflictError", async () => {
    globalThis.fetch = vi.fn(
      async () =>
        new Response(JSON.stringify({ detail: "companion_name_taken" }), {
          status: 409,
          headers: { "Content-Type": "application/json" },
        }),
    ) as unknown as typeof fetch;

    await expect(createCompanion(CREATE_BODY)).rejects.toMatchObject({
      name: "CompanionConflictError",
      kind: "companion_name_taken",
    });
  });

  it("create surfaces 409 companion_limit_reached as CompanionConflictError", async () => {
    globalThis.fetch = vi.fn(
      async () =>
        new Response(JSON.stringify({ detail: "companion_limit_reached" }), { status: 409 }),
    ) as unknown as typeof fetch;

    await expect(createCompanion(CREATE_BODY)).rejects.toBeInstanceOf(CompanionConflictError);
  });

  it("update PUTs the body and parses the response", async () => {
    const spy = vi.fn(
      async (_input: Parameters<typeof fetch>[0], _init?: Parameters<typeof fetch>[1]) =>
        new Response(JSON.stringify(COMPANION), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
    );
    globalThis.fetch = spy as unknown as typeof fetch;

    await updateCompanion(COMPANION.id, CREATE_BODY);
    const call = spy.mock.calls[0];
    const init = (call?.[1] ?? {}) as RequestInit;
    expect(init.method).toBe("PUT");
    const url = String((call as unknown as [string])?.[0]);
    expect(url).toContain(`/api/companions/${COMPANION.id}`);
  });

  it("update propagates 404 as plain ApiError", async () => {
    globalThis.fetch = vi.fn(
      async () => new Response(JSON.stringify({ detail: "companion_not_found" }), { status: 404 }),
    ) as unknown as typeof fetch;

    await expect(updateCompanion(COMPANION.id, CREATE_BODY)).rejects.toBeInstanceOf(ApiError);
  });

  it("delete sends DELETE and resolves on 204", async () => {
    const spy = vi.fn(
      async (_input: Parameters<typeof fetch>[0], _init?: Parameters<typeof fetch>[1]) =>
        new Response(null, { status: 204 }),
    );
    globalThis.fetch = spy as unknown as typeof fetch;

    await deleteCompanion(COMPANION.id);
    const call = spy.mock.calls[0];
    const init = (call?.[1] ?? {}) as RequestInit;
    expect(init.method).toBe("DELETE");
  });
});
