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

  // Scrapbook voice (VOICE.md): status is rendered as a colored signal dot +
  // verdict copy, NEVER as a pill labelled "Complete"/"Running"/"Aborted".
  it("renders the 'pinned ★' verdict for complete trips and the done signal color", () => {
    const html = renderToString(<TripCard trip={SAMPLE} />);
    expect(html).toContain("pinned ★");
    expect(html).toContain("hsl(var(--signal-done))");
    expect(html).not.toContain("Complete");
  });

  it("renders a link to the trip detail route", () => {
    const html = renderToString(<TripCard trip={SAMPLE} />);
    expect(html).toMatch(/href="\/app\/trips\/11111111-2222-4333-8444-555555555555"/);
  });

  it("renders a <time> element with the ISO dateTime attr (effect-mounted label is empty on SSR)", () => {
    const html = renderToString(<TripCard trip={SAMPLE} />);
    expect(html).toMatch(/<time[^>]+datetime="2026-05-20T14:30:00\+00:00"/i);
  });

  it("renders the snag signal color + 'hit a wall' verdict for aborted trips", () => {
    const html = renderToString(<TripCard trip={{ ...SAMPLE, status: "aborted" }} />);
    expect(html).toContain("hit a wall");
    expect(html).toContain("hsl(var(--signal-snag))");
    expect(html).not.toContain("Aborted");
  });

  it("renders the live signal (with pulse animation) and 'still scribbling' for running trips", () => {
    const html = renderToString(<TripCard trip={{ ...SAMPLE, status: "running" }} />);
    expect(html).toContain("still scribbling");
    expect(html).toContain("hsl(var(--signal-live))");
    expect(html).toContain("animation:pulse");
    expect(html).not.toContain("Running");
  });
});
