import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { deleteMe, exportMe, parseFilenameFromDisposition } from "@/lib/api/me";
import { ApiError } from "@/lib/api/client";
import { useAuthStore } from "@/store/auth";

const originalFetch = globalThis.fetch;

describe("parseFilenameFromDisposition", () => {
  it("returns the filename when wrapped in quotes", () => {
    expect(
      parseFilenameFromDisposition('attachment; filename="plus-one-export-abc-2026-05-22.json"'),
    ).toBe("plus-one-export-abc-2026-05-22.json");
  });

  it("falls back to bare filename when unquoted", () => {
    expect(parseFilenameFromDisposition("attachment; filename=foo.json")).toBe("foo.json");
  });

  it("returns null on missing header", () => {
    expect(parseFilenameFromDisposition(null)).toBeNull();
  });
});

describe("exportMe", () => {
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

  it("calls GET /api/me/export with the bearer token", async () => {
    const blob = new Blob(["{}"], { type: "application/json" });
    const spy = vi.fn(
      async (_input: Parameters<typeof fetch>[0], _init?: Parameters<typeof fetch>[1]) => {
        const headers = new Headers({
          "Content-Type": "application/json",
          "Content-Disposition": 'attachment; filename="plus-one-export-u-2026-05-22.json"',
        });
        return new Response(blob, { status: 200, headers });
      },
    );
    globalThis.fetch = spy as unknown as typeof fetch;

    await exportMe();

    expect(spy).toHaveBeenCalledOnce();
    const call = spy.mock.calls[0];
    expect(call).toBeDefined();
    const init = (call?.[1] ?? {}) as RequestInit;
    expect(init.method).toBe("GET");
    const sentHeaders = init.headers as Record<string, string>;
    expect(sentHeaders.Authorization).toBe("Bearer jwt");
  });

  it("throws ApiError on a non-2xx response", async () => {
    globalThis.fetch = vi.fn(
      async () => new Response("nope", { status: 500 }),
    ) as unknown as typeof fetch;
    await expect(exportMe()).rejects.toBeInstanceOf(ApiError);
  });
});

describe("deleteMe", () => {
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

  it("resolves on 204", async () => {
    globalThis.fetch = vi.fn(
      async () => new Response(null, { status: 204 }),
    ) as unknown as typeof fetch;
    await expect(deleteMe()).resolves.toBeUndefined();
  });

  it("throws ApiError(409, admin_cannot_self_delete) on conflict", async () => {
    globalThis.fetch = vi.fn(
      async () =>
        new Response(JSON.stringify({ detail: "admin_cannot_self_delete" }), {
          status: 409,
          headers: { "Content-Type": "application/json" },
        }),
    ) as unknown as typeof fetch;
    try {
      await deleteMe();
      throw new Error("expected ApiError");
    } catch (err) {
      expect(err).toBeInstanceOf(ApiError);
      const e = err as ApiError;
      expect(e.status).toBe(409);
      expect(e.message).toBe("admin_cannot_self_delete");
    }
  });

  it("throws ApiError on other non-2xx", async () => {
    globalThis.fetch = vi.fn(
      async () => new Response("x", { status: 500 }),
    ) as unknown as typeof fetch;
    await expect(deleteMe()).rejects.toBeInstanceOf(ApiError);
  });
});
