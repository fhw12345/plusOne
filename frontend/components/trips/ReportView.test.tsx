import { beforeEach, describe, expect, it } from "vitest";
import { renderToString } from "react-dom/server";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { ReportView } from "@/components/trips/ReportView";
import type { TripDetail } from "@/lib/schemas/trips";
import { useReportPrefsStore } from "@/store/reportPrefs";

function renderWithProviders(node: React.ReactElement): string {
  // ReportView (batch-2p) reads ``useCurrentUser`` / ``useCompanions``
  // via TanStack Query. SSR rendering still walks those hooks, so the
  // tests must hand in a QueryClient even though both queries are
  // ``enabled: false`` (no auth token in test).
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return renderToString(
    <QueryClientProvider client={client}>{node}</QueryClientProvider>,
  );
}

function trip(items: Array<Record<string, unknown>>): TripDetail {
  return {
    trip_id: "11111111-2222-4333-8444-555555555555",
    destination: "Tokyo",
    status: "complete",
    latest_report_id: "11111111-2222-4333-8444-666666666666",
    content: { items },
  };
}

const AGREE_GEM = {
  candidate: { name: "Menya Itto" },
  classification: "local_gem",
  classification_en: "local_gem",
  classification_zh: "local_gem",
  confidence: 0.8,
  divergence_score: 0,
};

const EN_ONLY = {
  candidate: { name: "Reddit Favorite" },
  classification: "local_gem",
  classification_en: "local_gem",
  classification_zh: null,
  confidence: 0.6,
  divergence_score: 0,
};

const DISAGREE = {
  candidate: { name: "Disputed Spot" },
  classification: "local_gem",
  classification_en: "local_gem",
  classification_zh: "tourist_trap",
  confidence: 0.7,
  divergence_score: 1.0,
};

describe("ReportView (SSR markup)", () => {
  beforeEach(() => {
    useReportPrefsStore.setState({ perspective: "fused" });
  });

  it("renders the perspective toggle even when there are no items", () => {
    const html = renderWithProviders(<ReportView trip={trip([])} />);
    expect(html).toMatch(/data-testid="perspective-toggle"/);
  });

  it("renders the perspective toggle alongside items", () => {
    const html = renderWithProviders(<ReportView trip={trip([AGREE_GEM])} />);
    expect(html).toMatch(/data-testid="perspective-toggle"/);
    expect(html).toContain("Menya Itto");
  });

  it("renders the disagreement tab label (scrapbook voice)", () => {
    const html = renderWithProviders(<ReportView trip={trip([AGREE_GEM])} />);
    // Tab is labelled "two minds" in scrapbook voice — see TAB_LABELS in
    // lib/trips/categorize.ts. Avoid the literal "Disagreement" pill word.
    expect(html).toContain("two minds");
  });

  it("includes disagreement items in the disagreement bucket name list", () => {
    // The default 'together' tab is the visible one on SSR; other tab
    // panes also serialize to markup (hidden via data-state), so we can
    // assert that the disputed item's name shows up in the rendered HTML.
    const html = renderWithProviders(<ReportView trip={trip([AGREE_GEM, DISAGREE])} />);
    expect(html).toContain("Disputed Spot");
  });

  it("renders items that lack per-language fields under fused", () => {
    const oldItem = {
      candidate: { name: "Legacy Item" },
      classification: "local_gem",
      confidence: 0.5,
    };
    const html = renderWithProviders(<ReportView trip={trip([oldItem])} />);
    expect(html).toContain("Legacy Item");
  });

  it("includes the per-language badges on items that have them", () => {
    const html = renderWithProviders(<ReportView trip={trip([DISAGREE])} />);
    expect(html).toMatch(/data-perlang="en"/);
    expect(html).toMatch(/data-perlang="zh"/);
  });

  it("omits per-language badges when a side is null (EN-only item)", () => {
    const html = renderWithProviders(<ReportView trip={trip([EN_ONLY])} />);
    expect(html).toMatch(/data-perlang="en"/);
    expect(html).not.toMatch(/data-perlang="zh"/);
  });
});
