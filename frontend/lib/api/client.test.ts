import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, apiFetch } from "@/lib/api/client";
import { useAuthStore } from "@/store/auth";

const originalFetch = globalThis.fetch;

describe("apiFetch", () => {
  beforeEach(() => {
    useAuthStore.setState({ token: null, user: null });
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it("returns parsed JSON for 2xx", async () => {
    globalThis.fetch = vi.fn(
      async () =>
        new Response(JSON.stringify({ ok: true }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
    ) as unknown as typeof fetch;

    const result = await apiFetch<{ ok: boolean }>("/api/x", { method: "GET" });
    expect(result).toEqual({ ok: true });
  });

  it("injects Authorization header when a token is in the store", async () => {
    useAuthStore.getState().setSession("jwt-token", {
      id: "u1",
      email: "a@b.test",
      username: "u1",
      is_admin: false,
    });
    const spy = vi.fn(
      async (_input: Parameters<typeof fetch>[0], _init?: Parameters<typeof fetch>[1]) =>
        new Response(JSON.stringify({ ok: true }), { status: 200 }),
    );
    globalThis.fetch = spy as unknown as typeof fetch;

    await apiFetch("/api/x", { method: "GET" });

    expect(spy).toHaveBeenCalledTimes(1);
    const init = (spy.mock.calls[0]?.[1] ?? {}) as RequestInit;
    const headers = init.headers as Record<string, string>;
    expect(headers.Authorization).toBe("Bearer jwt-token");
  });

  it("omits Authorization when no token", async () => {
    const spy = vi.fn(
      async (_input: Parameters<typeof fetch>[0], _init?: Parameters<typeof fetch>[1]) =>
        new Response(JSON.stringify({ ok: true }), { status: 200 }),
    );
    globalThis.fetch = spy as unknown as typeof fetch;

    await apiFetch("/api/x", { method: "GET" });

    const init = (spy.mock.calls[0]?.[1] ?? {}) as RequestInit;
    const headers = init.headers as Record<string, string>;
    expect(headers.Authorization).toBeUndefined();
  });

  it("returns undefined for 204 No Content", async () => {
    globalThis.fetch = vi.fn(
      async () => new Response(null, { status: 204 }),
    ) as unknown as typeof fetch;

    const result = await apiFetch("/api/x", { method: "POST", body: "{}" });
    expect(result).toBeUndefined();
  });

  it("throws ApiError on non-2xx with parsed body", async () => {
    globalThis.fetch = vi.fn(
      async () =>
        new Response(JSON.stringify({ detail: "nope" }), {
          status: 400,
          headers: { "Content-Type": "application/json" },
        }),
    ) as unknown as typeof fetch;

    await expect(apiFetch("/api/x", { method: "GET" })).rejects.toMatchObject({
      name: "ApiError",
      status: 400,
      message: "nope",
    });
  });

  it("clears stale auth and redirects to login on 401", async () => {
    useAuthStore.getState().setSession("expired-token", {
      id: "u1",
      email: "a@b.test",
      username: "u1",
      is_admin: false,
    });
    const assign = vi.fn();
    vi.stubGlobal("window", {
      location: { pathname: "/app", assign },
    });
    globalThis.fetch = vi.fn(
      async () => new Response(JSON.stringify({ detail: "expired" }), { status: 401 }),
    ) as unknown as typeof fetch;

    await expect(apiFetch("/api/auth/me", { method: "GET" })).rejects.toMatchObject({
      status: 401,
    });

    expect(useAuthStore.getState().token).toBeNull();
    expect(assign).toHaveBeenCalledWith("/login");
  });

  it("does not clear the current form state for failed password login", async () => {
    useAuthStore.getState().setSession("still-present", {
      id: "u1",
      email: "a@b.test",
      username: "u1",
      is_admin: false,
    });
    const assign = vi.fn();
    vi.stubGlobal("window", {
      location: { pathname: "/login", assign },
    });
    globalThis.fetch = vi.fn(
      async () => new Response(JSON.stringify({ detail: "invalid_credentials" }), { status: 401 }),
    ) as unknown as typeof fetch;

    await expect(apiFetch("/api/auth/login", { method: "POST", body: "{}" })).rejects.toMatchObject(
      { status: 401 },
    );

    expect(useAuthStore.getState().token).toBe("still-present");
    expect(assign).not.toHaveBeenCalled();
  });

  it("ApiError carries status and body fields", async () => {
    globalThis.fetch = vi.fn(
      async () => new Response(JSON.stringify({ detail: "boom" }), { status: 503 }),
    ) as unknown as typeof fetch;

    try {
      await apiFetch("/api/x", { method: "GET" });
      throw new Error("should have thrown");
    } catch (err) {
      expect(err).toBeInstanceOf(ApiError);
      const apiErr = err as ApiError;
      expect(apiErr.status).toBe(503);
      expect(apiErr.body).toEqual({ detail: "boom" });
    }
  });

  it("turns a hung request into request_timeout", async () => {
    vi.useFakeTimers();
    globalThis.fetch = vi.fn(
      (_input: Parameters<typeof fetch>[0], init?: Parameters<typeof fetch>[1]) =>
        new Promise<Response>((_resolve, reject) => {
          init?.signal?.addEventListener("abort", () =>
            reject(new DOMException("aborted", "AbortError")),
          );
        }),
    ) as unknown as typeof fetch;

    const pending = apiFetch("/api/x", { method: "GET" });
    const assertion = expect(pending).rejects.toMatchObject({
      name: "ApiError",
      status: 408,
      message: "request_timeout",
    });
    await vi.advanceTimersByTimeAsync(20_000);

    await assertion;
    vi.useRealTimers();
  });
});
