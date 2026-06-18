import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderToString } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { ItineraryView } from "@/components/trips/ItineraryView";
import type { TripDetail } from "@/lib/schemas/trips";

function renderWithProviders(node: React.ReactElement): string {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return renderToString(<QueryClientProvider client={client}>{node}</QueryClientProvider>);
}

function trip(): TripDetail {
  return {
    trip_id: "11111111-2222-4333-8444-555555555555",
    destination: "Tokyo",
    status: "complete",
    latest_report_id: "11111111-2222-4333-8444-666666666666",
    content: {
      tl_dr: "Tokyo has two stronger ramen anchors and one maybe.",
      items: [
        {
          candidate: { name: "Menya Itto", rationale: "real local tsukemen signal" },
          classification: "local_gem",
          classification_en: "local_gem",
          classification_zh: "neutral",
          confidence: 0.82,
          evidence: [
            {
              source: "xiaohongshu",
              url: "https://www.xiaohongshu.com/explore/1",
              snippet: "东京 Menya Itto 本地人排队, 值得去。",
            },
          ],
          summary: "Strong source match.",
          image_url: "https://img.example/itto.jpg",
        },
      ],
      day_plan: [
        {
          day_index: 1,
          theme: "ramen counters",
          slots: [{ period: "morning", item_index: 0, note: "start here" }],
        },
      ],
    },
  };
}

describe("ItineraryView", () => {
  it("renders a trip-level takeaway and per-card decision value", () => {
    const html = renderWithProviders(<ItineraryView trip={trip()} />);

    expect(html).toMatch(/data-testid="itinerary-tldr"/);
    expect(html).toContain("Tokyo has two stronger ramen anchors and one maybe.");
    expect(html).toContain("Worth anchoring the day around if the route works.");
    expect(html).toContain("why");
    expect(html).toContain("real local tsukemen signal");
  });

  it("keeps source notes collapsed by default", () => {
    const html = renderWithProviders(<ItineraryView trip={trip()} />);

    expect(html).toContain("<details");
    expect(html).not.toContain("<details open");
    expect(html).toMatch(/source notes \([^)]*1[^)]*\)/);
  });

  it("routes brittle XHS note links through a public search link", () => {
    const html = renderWithProviders(<ItineraryView trip={trip()} />);

    expect(html).toContain("xhs search");
    expect(html).toContain("https://www.google.com/search?q=");
    expect(html).not.toContain('href="https://www.xiaohongshu.com/explore/1"');
  });
});
