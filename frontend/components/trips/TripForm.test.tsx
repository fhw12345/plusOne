import { describe, expect, it, vi } from "vitest";
import { renderToString } from "react-dom/server";

// Batch-2o: TripForm uses next/navigation's ``useRouter`` at module
// scope. Stub it for SSR rendering — we never actually navigate here;
// the assertions are markup-only (same pattern as
// DestinationCombobox.test.tsx, since the repo doesn't ship jsdom).
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: () => {}, replace: () => {}, refresh: () => {} }),
}));

// useCityIndex is consumed by DestinationCombobox which TripForm renders.
vi.mock("@/hooks/useCityIndex", () => ({
  useCityIndex: () => ({ status: "loading" }),
}));

// CompanionSelector reaches for the companions API via ``useCompanions``
// (react-query); stub the hook so SSR doesn't try to spin up a
// QueryClient just for these structural assertions.
vi.mock("@/lib/api/companions", () => ({
  listCompanions: async () => [],
}));
vi.mock("@/hooks/useCompanions", () => ({
  useCompanions: () => ({ data: { companions: [] }, isLoading: false, error: null }),
  COMPANIONS_KEY: ["companions"],
}));

import { TripForm } from "@/components/trips/TripForm";

describe("TripForm (SSR markup) — batch-2o dates + budget", () => {
  it("renders the new `when` block with from / to date inputs", () => {
    const html = renderToString(<TripForm />);
    expect(html).toContain(">when<");
    expect(html).toContain('id="date_start"');
    expect(html).toContain('id="date_end"');
    expect(html).toMatch(/type="date"[^>]*id="date_start"|id="date_start"[^>]*type="date"/);
  });

  it("renders the budget block with amount + currency select", () => {
    const html = renderToString(<TripForm />);
    expect(html).toContain(">your budget<");
    expect(html).toContain('id="budget_amount"');
    expect(html).toContain('id="budget_currency"');
    expect(html).toContain('placeholder="2500"');
  });

  it("lists USD first so it's the natural fallback selection", () => {
    const html = renderToString(<TripForm />);
    // The SSR select has no per-option `selected` attribute (RHF wires
    // the default via state, not markup). USD being first means it's
    // what the browser shows + what the form posts on a no-op submit.
    const selectMatch = html.match(/<select[^>]*id="budget_currency"[^>]*>([\s\S]*?)<\/select>/);
    expect(selectMatch).not.toBeNull();
    expect(selectMatch?.[1]).toMatch(/^<option[^>]*value="USD"/);
  });

  it("renders all whitelisted currency options", () => {
    const html = renderToString(<TripForm />);
    for (const code of ["USD", "EUR", "JPY", "CNY", "GBP", "TWD", "KRW", "AUD"]) {
      expect(html).toContain(`value="${code}"`);
    }
  });

  it("keeps existing TripForm content alongside the new fields", () => {
    const html = renderToString(<TripForm />);
    // Place combobox (batch-2n) still present.
    expect(html).toContain(">the place<");
    // Companions section still present (uses a smart quote, not &#x2019;).
    expect(html).toContain(">who you’re bringing<");
    // Free-text mood textarea still present.
    expect(html).toContain('id="mood"');
  });

  it("shows the optional hint copy for both new blocks", () => {
    const html = renderToString(<TripForm />);
    expect(html).toContain("optional. skip if you haven");
    expect(html).toContain("optional. round numbers are fine");
  });
});
