import { describe, it, expect } from "vitest";

import { TripEvent } from "@/lib/schemas/events";

describe("TripEvent", () => {
  it("parses a started event", () => {
    const parsed = TripEvent.parse({ name: "started", trip_id: "abc-123" });
    expect(parsed.name).toBe("started");
  });

  it("parses a producer event with expected data shape", () => {
    const parsed = TripEvent.parse({
      name: "producer",
      depth: 1,
      data: { n_candidates: 5, notes: "in_tokens=100 out_tokens=50" },
    });
    if (parsed.name === "producer") {
      expect(parsed.data.n_candidates).toBe(5);
    } else {
      throw new Error("expected producer");
    }
  });

  it("parses a controller event and narrows on name", () => {
    const parsed = TripEvent.parse({
      name: "controller",
      depth: 2,
      data: { should_continue: false, reasoning: "enough", notes: "" },
    });
    if (parsed.name === "controller") {
      expect(parsed.data.should_continue).toBe(false);
    } else {
      throw new Error("expected controller");
    }
  });

  it("parses cycle_aborted with reason", () => {
    const parsed = TripEvent.parse({
      name: "cycle_aborted",
      depth: 1,
      data: { reason: "no_data" },
    });
    if (parsed.name === "cycle_aborted") {
      expect(parsed.data.reason).toBe("no_data");
    } else {
      throw new Error("expected cycle_aborted");
    }
  });

  it("parses trip_complete with nullable report_id", () => {
    const parsed = TripEvent.parse({
      name: "trip_complete",
      trip_id: "abc",
      status: "complete",
      report_id: null,
    });
    expect(parsed.name).toBe("trip_complete");
  });

  it("tolerates unknown extra fields via passthrough", () => {
    const parsed = TripEvent.parse({
      name: "started",
      trip_id: "abc",
      future_field: "ok",
    });
    expect(parsed.name).toBe("started");
  });

  it("rejects an unknown event name", () => {
    expect(TripEvent.safeParse({ name: "bogus" }).success).toBe(false);
  });
});
