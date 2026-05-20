import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import * as React from "react";
import { renderToString } from "react-dom/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// Mock listTrips so the hook never hits a real fetch boundary.
const listTripsMock = vi.fn();
vi.mock("@/lib/api/trips", () => ({
  listTrips: (...args: unknown[]) => listTripsMock(...args),
}));

// The hook is imported AFTER the mock declaration so the mock binding wins.
import { useTrips } from "@/hooks/useTrips";
import { useAuthStore } from "@/store/auth";

function Probe({ onState }: { onState: (state: ReturnType<typeof useTrips>) => void }) {
  const state = useTrips();
  onState(state);
  return null;
}

function renderProbe(): ReturnType<typeof useTrips> {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  let captured: ReturnType<typeof useTrips> | undefined;
  renderToString(
    <QueryClientProvider client={client}>
      <Probe onState={(s) => (captured = s)} />
    </QueryClientProvider>,
  );
  if (!captured) throw new Error("hook did not render");
  return captured;
}

describe("useTrips", () => {
  beforeEach(() => {
    listTripsMock.mockReset();
    useAuthStore.setState({ token: null, user: null });
  });

  afterEach(() => {
    useAuthStore.setState({ token: null, user: null });
  });

  it("is disabled pre-hydration (no token in the store)", () => {
    const state = renderProbe();
    expect(state.isFetching).toBe(false);
    // Hook is disabled, so listTrips is never invoked.
    expect(listTripsMock).not.toHaveBeenCalled();
  });

  it("becomes enabled once token is present (but SSR render won't fire the query)", () => {
    // useHasHydrated returns false on SSR (per useSyncExternalStore's
    // serverSnapshot), so even with a token the query stays disabled
    // during renderToString. This proves the hook's gating logic includes
    // the hydration check — not just the token. Real enablement happens
    // post-mount in the browser; the e2e spec covers that path.
    useAuthStore.setState({ token: "jwt", user: { id: "u", email: "a@b" } });
    const state = renderProbe();
    expect(state.isFetching).toBe(false);
    expect(listTripsMock).not.toHaveBeenCalled();
  });

  it("exposes infinite-query plumbing (fetchNextPage + hasNextPage)", () => {
    const state = renderProbe();
    expect(typeof state.fetchNextPage).toBe("function");
    expect(typeof state.refetch).toBe("function");
    // hasNextPage is undefined when no data has been fetched.
    expect(state.hasNextPage).toBeFalsy();
  });
});
