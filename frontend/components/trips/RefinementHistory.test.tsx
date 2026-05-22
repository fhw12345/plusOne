import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import * as React from "react";
import { renderToString } from "react-dom/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// Mock the hook so we can SSR-render the component with arbitrary data
// without having to seed react-query or the auth store.
const useTripReportsMock = vi.fn();
vi.mock("@/hooks/useTripReports", () => ({
  useTripReports: (...args: unknown[]) => useTripReportsMock(...args),
}));

import { RefinementHistory } from "@/components/trips/RefinementHistory";

function withClient(node: React.ReactElement): string {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return renderToString(<QueryClientProvider client={client}>{node}</QueryClientProvider>);
}

const TRIP_ID = "11111111-2222-4333-8444-555555555555";

const ORIGINAL = {
  report_id: "r1",
  created_at: "2026-05-20T10:00:00Z",
  is_original: true,
  hint: null,
  previous_report_id: null,
};
const REFINE_V2 = {
  report_id: "r2",
  created_at: "2026-05-21T10:00:00Z",
  is_original: false,
  hint: "swap kiyomizu",
  previous_report_id: "r1",
};
const REFINE_V3 = {
  report_id: "r3",
  created_at: "2026-05-22T10:00:00Z",
  is_original: false,
  hint: "quieter pace overall",
  previous_report_id: "r2",
};

beforeEach(() => {
  useTripReportsMock.mockReset();
});

afterEach(() => {
  useTripReportsMock.mockReset();
});

describe("RefinementHistory (SSR markup)", () => {
  it("renders the header in all states", () => {
    useTripReportsMock.mockReturnValue({ data: { reports: [ORIGINAL] } });
    const html = withClient(<RefinementHistory tripId={TRIP_ID} />);
    expect(html).toContain("past tweaks");
  });

  it("renders the empty-state line when only the original exists", () => {
    useTripReportsMock.mockReturnValue({ data: { reports: [ORIGINAL] } });
    const html = withClient(<RefinementHistory tripId={TRIP_ID} />);
    expect(html).toMatch(/data-testid="refinement-history-empty"/);
    expect(html).toContain("no tweaks yet. this is the original.");
  });

  it("renders the empty-state line when there are no reports at all", () => {
    useTripReportsMock.mockReturnValue({ data: { reports: [] } });
    const html = withClient(<RefinementHistory tripId={TRIP_ID} />);
    expect(html).toMatch(/data-testid="refinement-history-empty"/);
  });

  it("renders three rows in chronological order with v-labels", () => {
    useTripReportsMock.mockReturnValue({
      data: { reports: [ORIGINAL, REFINE_V2, REFINE_V3] },
    });
    const html = withClient(<RefinementHistory tripId={TRIP_ID} currentReportId="r3" />);
    const rows = html.match(/data-testid="refinement-history-row"/g) ?? [];
    expect(rows).toHaveLength(3);
    expect(html).toContain("v1 — the original");
    expect(html).toContain("v2 — swap kiyomizu");
    expect(html).toContain("v3 — quieter pace overall");
  });

  it("marks the current row and renders CTAs on the others", () => {
    useTripReportsMock.mockReturnValue({
      data: { reports: [ORIGINAL, REFINE_V2, REFINE_V3] },
    });
    const html = withClient(<RefinementHistory tripId={TRIP_ID} currentReportId="r3" />);
    // Exactly one marker for the current row.
    const markers = html.match(/data-testid="refinement-history-current"/g) ?? [];
    expect(markers).toHaveLength(1);
    expect(html).toContain("↑ showing this one");
    // Two non-current rows render the CTA.
    const ctas = html.match(/data-testid="refinement-history-show"/g) ?? [];
    expect(ctas).toHaveLength(2);
    expect(html).toContain("show this version");
  });

  it("defaults the current row to the newest when currentReportId is null", () => {
    useTripReportsMock.mockReturnValue({
      data: { reports: [ORIGINAL, REFINE_V2, REFINE_V3] },
    });
    const html = withClient(<RefinementHistory tripId={TRIP_ID} />);
    // r3 is the newest → exactly one marker (the last row).
    const markers = html.match(/data-testid="refinement-history-current"/g) ?? [];
    expect(markers).toHaveLength(1);
    // Verify the marker is in the v3 row (last row of the rendered list).
    const lastRowMatch = html.match(
      /data-testid="refinement-history-row"[^]*?(?=data-testid="refinement-history-row"|<\/ul>)/g,
    );
    expect(lastRowMatch).toBeTruthy();
    const lastRow = lastRowMatch?.[lastRowMatch.length - 1] ?? "";
    expect(lastRow).toContain("v3");
    expect(lastRow).toContain("refinement-history-current");
  });

  it("truncates long hints in the row label", () => {
    const longHint = "a".repeat(120);
    useTripReportsMock.mockReturnValue({
      data: {
        reports: [
          ORIGINAL,
          { ...REFINE_V2, hint: longHint },
        ],
      },
    });
    const html = withClient(<RefinementHistory tripId={TRIP_ID} currentReportId="r2" />);
    // Truncated label ends with the ellipsis character.
    expect(html).toContain("…");
    // Full 120-char hint shouldn't be rendered verbatim.
    expect(html.includes(longHint)).toBe(false);
  });

  it("treats undefined data as empty (loading state) without crashing", () => {
    useTripReportsMock.mockReturnValue({ data: undefined });
    const html = withClient(<RefinementHistory tripId={TRIP_ID} />);
    expect(html).toContain("past tweaks");
  });

  it("never emits banned phrases", () => {
    useTripReportsMock.mockReturnValue({
      data: { reports: [ORIGINAL, REFINE_V2] },
    });
    const html = withClient(<RefinementHistory tripId={TRIP_ID} currentReportId="r2" />);
    expect(html).not.toMatch(/Loading…/);
    expect(html).not.toMatch(/Powered by AI/);
  });
});
