import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { renderToString } from "react-dom/server";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
    refresh: vi.fn(),
    back: vi.fn(),
    forward: vi.fn(),
    prefetch: vi.fn(),
  }),
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({}),
  usePathname: () => "/admin/logs",
}));

import AdminLogsPage from "@/app/admin/logs/page";
import { useAuthStore } from "@/store/auth";

// The page is gated behind useCurrentUser + is_admin. The SSR snapshot below
// only checks that the gate-fallback renders cleanly for non-admin / signed-
// out callers, and that the page module itself does not include banned
// phrases at the source level.

function renderWithProviders(): string {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return renderToString(
    <QueryClientProvider client={qc}>
      <AdminLogsPage />
    </QueryClientProvider>,
  );
}

describe("AdminLogsPage (SSR markup)", () => {
  beforeEach(() => {
    useAuthStore.setState({ token: null, user: null });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders the one-sec fallback when no token is present (signed-out gate)", () => {
    const html = renderWithProviders();
    // Signed-out callers should never see the actual log panes during SSR.
    expect(html).not.toContain("the wire (admin)");
    expect(html).toContain("one sec");
  });

  it("does not include banned phrases at source render time", () => {
    const html = renderWithProviders();
    expect(html).not.toContain("Submitting…");
    expect(html).not.toContain("Loading…");
    expect(html).not.toContain("Powered by AI");
    expect(html).not.toMatch(/\bStatus\b/);
  });
});
