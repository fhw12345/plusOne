import { beforeEach, describe, expect, it } from "vitest";
import { renderToString } from "react-dom/server";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { ReportView } from "@/components/trips/ReportView";
import type { TripDetail } from "@/lib/schemas/trips";
import { useReportPrefsStore } from "@/store/reportPrefs";

function renderWithProviders(node: React.ReactElement): string {
  // Batch-2p: ReportView now reads ``useCurrentUser`` / ``useCompanions``
  // even though both are auth-gated (and disabled here). A QueryClient
  // must be in scope or the hooks throw on first render.
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return renderToString(
    <QueryClientProvider client={client}>{node}</QueryClientProvider>,
  );
}

function trip(
  items: Array<Record<string, unknown>>,
  translations?: { en?: Array<Record<string, unknown>>; zh?: Array<Record<string, unknown>> },
): TripDetail {
  // Batch-2q widened per-lang translations to `{items, tl_dr}` (object).
  // The zod schema accepts bare arrays at the wire boundary via a
  // ``.transform()``; the inferred output type only carries the object
  // shape. Tests build a TripDetail directly (no schema parse) so we
  // wrap the test fixture's bare arrays in ``{items}`` to satisfy types
  // — same code path either way because resolveItems also accepts the
  // post-transform object form.
  const wrapped = translations
    ? {
        en: translations.en ? { items: translations.en } : undefined,
        zh: translations.zh ? { items: translations.zh } : undefined,
      }
    : undefined;
  return {
    trip_id: "11111111-2222-4333-8444-555555555555",
    destination: "Tokyo",
    status: "complete",
    latest_report_id: "11111111-2222-4333-8444-666666666666",
    content: { items, ...(wrapped ? { translations: wrapped } : {}) },
  };
}

const ORIGINAL = {
  candidate: { name: "Original Name" },
  classification: "local_gem",
  classification_en: "local_gem",
  classification_zh: "local_gem",
  confidence: 0.8,
  divergence_score: 0,
};

const EN_TRANSLATED = {
  candidate: { name: "Translated EN Name" },
  classification: "local_gem",
  classification_en: "local_gem",
  classification_zh: "local_gem",
  confidence: 0.8,
  divergence_score: 0,
};

const ZH_TRANSLATED = {
  candidate: { name: "翻译过的中文名" },
  classification: "local_gem",
  classification_en: "local_gem",
  classification_zh: "local_gem",
  confidence: 0.8,
  divergence_score: 0,
};

describe("ReportView (language toggle)", () => {
  beforeEach(() => {
    useReportPrefsStore.setState({ perspective: "fused", language: "original" });
  });

  it("renders the language toggle alongside the perspective toggle", () => {
    const html = renderWithProviders(<ReportView trip={trip([])} />);
    expect(html).toMatch(/data-testid="language-toggle"/);
    expect(html).toMatch(/data-testid="perspective-toggle"/);
  });

  it("renders original items by default (pre-hydration SSR shows original)", () => {
    const t = trip([ORIGINAL], { en: [EN_TRANSLATED], zh: [ZH_TRANSLATED] });
    const html = renderWithProviders(<ReportView trip={t} />);
    // SSR snapshot uses 'original' because rehydrate hasn't fired
    expect(html).toContain("Original Name");
    expect(html).not.toContain("Translated EN Name");
    expect(html).not.toContain("翻译过的中文名");
  });

  it("falls back to original items when the report has no translations key", () => {
    // Old report (pre-batch-2k): no translations field at all.
    const t = trip([ORIGINAL]);
    const html = renderWithProviders(<ReportView trip={t} />);
    expect(html).toContain("Original Name");
    // Language toggle is still rendered so the UI is consistent.
    expect(html).toMatch(/data-testid="language-toggle"/);
  });

  it("renders the language toggle even when the report has no items", () => {
    const html = renderWithProviders(<ReportView trip={trip([])} />);
    expect(html).toMatch(/data-testid="language-toggle"/);
  });
});
