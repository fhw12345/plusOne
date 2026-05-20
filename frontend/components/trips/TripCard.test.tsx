import { describe, expect, it } from "vitest";
import { renderToString } from "react-dom/server";

import { TripCard } from "@/components/trips/TripCard";
import type { TripListItem } from "@/lib/schemas/trips";

const SAMPLE: TripListItem = {
  trip_id: "11111111-2222-4333-8444-555555555555",
  destination: "Tokyo",
  status: "complete",
  created_at: "2026-05-20T14:30:00+00:00",
  latest_report_id: "11111111-2222-4333-8444-666666666666",
  has_report: true,
};

describe("TripCard (SSR markup)", () => {
  it("renders the destination text", () => {
    const html = renderToString(<TripCard trip={SAMPLE} />);
    expect(html).toContain("Tokyo");
  });

  it("renders the status badge label for 'complete'", () => {
    const html = renderToString(<TripCard trip={SAMPLE} />);
    expect(html).toContain("Complete");
  });

  it("renders a link to the trip detail route", () => {
    const html = renderToString(<TripCard trip={SAMPLE} />);
    expect(html).toMatch(/href="\/app\/trips\/11111111-2222-4333-8444-555555555555"/);
  });

  it("renders a <time> element with the ISO dateTime attr (effect-mounted label is empty on SSR)", () => {
    const html = renderToString(<TripCard trip={SAMPLE} />);
    expect(html).toMatch(/<time[^>]+datetime="2026-05-20T14:30:00\+00:00"/i);
  });

  it("renders the muted-gray (not red) class palette for aborted trips", () => {
    const html = renderToString(<TripCard trip={{ ...SAMPLE, status: "aborted" }} />);
    expect(html).toContain("Aborted");
    expect(html).not.toMatch(/text-red|bg-red/);
  });

  it("renders 'Running' badge for in-progress trips", () => {
    const html = renderToString(<TripCard trip={{ ...SAMPLE, status: "running" }} />);
    expect(html).toContain("Running");
    expect(html).toMatch(/bg-blue/);
  });
});
