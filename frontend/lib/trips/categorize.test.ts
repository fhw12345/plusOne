import { describe, expect, it } from "vitest";

import type { JoinedItem } from "@/lib/schemas/trips";
import { categorize, TAB_ORDER } from "./categorize";

function item(over: Record<string, unknown> = {}): JoinedItem {
  return {
    candidate: { name: "Item", area: null, style: null, rationale: "" },
    classification: "neutral",
    confidence: 0.5,
    evidence: [],
    summary: "",
    ...over,
  } as JoinedItem;
}

describe("categorize", () => {
  it("returns all six tab keys, even when no items match", () => {
    const buckets = categorize([]);
    for (const key of TAB_ORDER) {
      expect(buckets[key]).toEqual([]);
    }
  });

  it("puts every item in together", () => {
    const items = [
      item(),
      item({ classification: "local_gem" }),
      item({ classification: "tourist_trap" }),
    ];
    const buckets = categorize(items);
    expect(buckets.together).toHaveLength(3);
  });

  it("filters local_gems by classification", () => {
    const gem = item({ classification: "local_gem", candidate: { name: "Gem" } });
    const trap = item({ classification: "tourist_trap" });
    const neutral = item();
    const buckets = categorize([gem, trap, neutral]);
    expect(buckets.local_gems).toEqual([gem]);
  });

  it("filters tourist_traps by classification", () => {
    const trap = item({ classification: "tourist_trap", candidate: { name: "Trap" } });
    const gem = item({ classification: "local_gem" });
    const buckets = categorize([trap, gem]);
    expect(buckets.tourist_traps).toEqual([trap]);
  });

  it("leaves user_only / partner_only / disagreement empty in v1", () => {
    const items = [
      item(),
      item({ classification: "local_gem" }),
      item({ classification: "tourist_trap" }),
    ];
    const buckets = categorize(items);
    expect(buckets.user_only).toEqual([]);
    expect(buckets.partner_only).toEqual([]);
    expect(buckets.disagreement).toEqual([]);
  });

  it("does not crash on items missing classification", () => {
    const minimal = { candidate: { name: "Bare" } } as unknown as JoinedItem;
    const buckets = categorize([minimal]);
    expect(buckets.together).toEqual([minimal]);
    expect(buckets.local_gems).toEqual([]);
    expect(buckets.tourist_traps).toEqual([]);
  });
});
