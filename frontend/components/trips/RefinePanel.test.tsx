import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import * as React from "react";
import { renderToString } from "react-dom/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// Mock the refine API at the module boundary so the panel never touches fetch.
const refineTripMock = vi.fn();
vi.mock("@/lib/api/trips", () => ({
  refineTrip: (...args: unknown[]) => refineTripMock(...args),
}));

import { RefinePanel } from "@/components/trips/RefinePanel";

function withClient(node: React.ReactElement): string {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return renderToString(<QueryClientProvider client={client}>{node}</QueryClientProvider>);
}

const TRIP_ID = "11111111-2222-4333-8444-555555555555";

describe("RefinePanel (SSR markup)", () => {
  beforeEach(() => {
    refineTripMock.mockReset();
  });

  afterEach(() => {
    refineTripMock.mockReset();
  });

  it("renders the scrapbook header copy", () => {
    const html = withClient(<RefinePanel tripId={TRIP_ID} />);
    expect(html).toContain("tweak it");
    expect(html).toContain("tell me what to change. one line.");
  });

  it("renders the textarea with the scrapbook placeholder", () => {
    const html = withClient(<RefinePanel tripId={TRIP_ID} />);
    expect(html).toMatch(/data-testid="refine-hint"/);
    expect(html).toContain("swap kyoto temple → arashiyama instead");
  });

  it("renders the submit button with the idle label and disabled (empty hint)", () => {
    const html = withClient(<RefinePanel tripId={TRIP_ID} />);
    expect(html).toContain("off i go again");
    expect(html).toMatch(/data-testid="refine-submit"[^>]*disabled/);
  });

  it("renders the submit button disabled when the disabled prop is true", () => {
    const html = withClient(<RefinePanel tripId={TRIP_ID} disabled />);
    expect(html).toMatch(/data-testid="refine-submit"[^>]*disabled/);
  });

  it("renders the maxLength cap on the textarea", () => {
    const html = withClient(<RefinePanel tripId={TRIP_ID} />);
    expect(html).toMatch(/maxlength="500"/i);
  });

  it("renders no error scrawl on first paint", () => {
    const html = withClient(<RefinePanel tripId={TRIP_ID} />);
    expect(html).not.toMatch(/data-testid="refine-error"/);
  });

  it("never emits the banned 'Loading…' phrase", () => {
    const html = withClient(<RefinePanel tripId={TRIP_ID} />);
    expect(html).not.toMatch(/Loading…/);
    expect(html).not.toMatch(/Submitting…/);
  });
});
