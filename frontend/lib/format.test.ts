import { describe, it, expect } from "vitest";

import { TRIP_STATUS_META, formatTripDate } from "@/lib/format";

describe("formatTripDate", () => {
  const base = Date.parse("2026-05-20T12:00:00Z");

  it("renders 'just now' for sub-minute deltas", () => {
    expect(formatTripDate("2026-05-20T11:59:30Z", base)).toBe("just now");
  });

  it("renders minutes for sub-hour deltas", () => {
    expect(formatTripDate("2026-05-20T11:55:00Z", base)).toMatch(/minute/);
  });

  it("renders hours for sub-day deltas", () => {
    expect(formatTripDate("2026-05-20T08:00:00Z", base)).toMatch(/hour/);
  });

  it("renders days for sub-week deltas", () => {
    expect(formatTripDate("2026-05-18T12:00:00Z", base)).toMatch(/day/);
  });

  it("renders absolute YYYY-MM-DD for >=7 day deltas", () => {
    expect(formatTripDate("2026-05-10T12:00:00Z", base)).toBe("2026-05-10");
  });

  it("renders absolute YYYY-MM-DD for very old trips", () => {
    expect(formatTripDate("2025-01-15T03:14:15Z", base)).toBe("2025-01-15");
  });
});

describe("TRIP_STATUS_META", () => {
  it("covers all trip statuses (incl. batch-2t clarifying)", () => {
    expect(Object.keys(TRIP_STATUS_META).sort()).toEqual([
      "aborted",
      "clarifying",
      "complete",
      "pending",
      "running",
    ]);
  });

  it("uses muted gray (not red) for aborted — see PRD §12.4", () => {
    const meta = TRIP_STATUS_META.aborted;
    expect(meta.label).toBe("Aborted");
    expect(meta.classes).not.toMatch(/red/);
    expect(meta.classes).toMatch(/foreground/);
  });

  it("uses blue tone for running", () => {
    expect(TRIP_STATUS_META.running.classes).toMatch(/blue/);
  });

  it("uses green tone for complete", () => {
    expect(TRIP_STATUS_META.complete.classes).toMatch(/green/);
  });
});
