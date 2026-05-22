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

  it("leaves user_only / partner_only empty in v1", () => {
    const items = [
      item(),
      item({ classification: "local_gem" }),
      item({ classification: "tourist_trap" }),
    ];
    const buckets = categorize(items);
    expect(buckets.user_only).toEqual([]);
    expect(buckets.partner_only).toEqual([]);
  });

  it("does not crash on items missing classification", () => {
    const minimal = { candidate: { name: "Bare" } } as unknown as JoinedItem;
    const buckets = categorize([minimal]);
    expect(buckets.together).toEqual([minimal]);
    expect(buckets.local_gems).toEqual([]);
    expect(buckets.tourist_traps).toEqual([]);
  });

  // --- Per-perspective routing (PRD batch-2r §6) ---

  describe("perspective routing", () => {
    const splitItem = item({
      candidate: { name: "Split" },
      classification: "local_gem",
      classification_zh: "neutral",
      classification_en: "local_gem",
    });
    const oldItem = item({
      candidate: { name: "Old" },
      classification: "local_gem",
      // pre-2i: no per-side fields
    });

    it("fused: routes by fused classification", () => {
      const buckets = categorize([splitItem], "fused");
      expect(buckets.local_gems).toEqual([splitItem]);
      expect(buckets.tourist_traps).toEqual([]);
    });

    it("zh: routes by classification_zh", () => {
      const buckets = categorize([splitItem], "zh");
      expect(buckets.local_gems).toEqual([]);
      expect(buckets.tourist_traps).toEqual([]);
    });

    it("en: routes by classification_en", () => {
      const buckets = categorize([splitItem], "en");
      expect(buckets.local_gems).toEqual([splitItem]);
      expect(buckets.tourist_traps).toEqual([]);
    });

    it("pre-2i item falls back to fused under every perspective (no items hidden)", () => {
      expect(categorize([oldItem], "fused").local_gems).toEqual([oldItem]);
      expect(categorize([oldItem], "zh").local_gems).toEqual([oldItem]);
      expect(categorize([oldItem], "en").local_gems).toEqual([oldItem]);
      // together always contains everything regardless of perspective
      expect(categorize([oldItem], "zh").together).toEqual([oldItem]);
      expect(categorize([oldItem], "en").together).toEqual([oldItem]);
    });

    it("disagreement membership is identical across perspectives", () => {
      const disagree = item({
        candidate: { name: "Disagree" },
        classification: "neutral",
        classification_en: "local_gem",
        classification_zh: "tourist_trap",
        divergence_score: 0.9,
      });
      const items = [splitItem, oldItem, disagree];
      const fused = categorize(items, "fused").disagreement;
      const zh = categorize(items, "zh").disagreement;
      const en = categorize(items, "en").disagreement;
      expect(fused).toEqual([disagree]);
      expect(zh).toEqual(fused);
      expect(en).toEqual(fused);
    });

    it("defaults perspective to fused when omitted (back-compat)", () => {
      const buckets = categorize([splitItem]);
      expect(buckets.local_gems).toEqual([splitItem]);
    });
  });

  // --- Per-person score routing (PRD batch-2p §6) ---

  describe("score routing", () => {
    const USER = "11111111-2222-4333-8444-555555555555";
    const ALICE = "22222222-3333-4444-8555-666666666666";
    const BOB = "33333333-4444-4555-8666-777777777777";

    const partyCouple = { user_id: USER, companion_ids: [ALICE] };
    const partySolo = { user_id: USER, companion_ids: [] };
    const partyTrio = { user_id: USER, companion_ids: [ALICE, BOB] };

    function scoredItem(scores: Record<string, number> | null, name = "Scored") {
      return item({
        candidate: { name },
        classification: "neutral",
        match_scores: scores,
      });
    }

    it("S1 couple, alice wants it / user doesn't → partner_only", () => {
      const sushi = scoredItem({ [USER]: 0.1, [ALICE]: 0.9 }, "Sushi");
      const buckets = categorize([sushi], "fused", partyCouple);
      expect(buckets.partner_only).toEqual([sushi]);
      expect(buckets.user_only).toEqual([]);
      // also still in together
      expect(buckets.together).toEqual([sushi]);
    });

    it("S1 couple, user wants it / alice doesn't → user_only", () => {
      const ramen = scoredItem({ [USER]: 0.85, [ALICE]: 0.2 }, "Ramen");
      const buckets = categorize([ramen], "fused", partyCouple);
      expect(buckets.user_only).toEqual([ramen]);
      expect(buckets.partner_only).toEqual([]);
    });

    it("S1 couple, both like it → neither score-gated tab", () => {
      const both = scoredItem({ [USER]: 0.7, [ALICE]: 0.7 }, "Together");
      const buckets = categorize([both], "fused", partyCouple);
      expect(buckets.user_only).toEqual([]);
      expect(buckets.partner_only).toEqual([]);
      expect(buckets.together).toEqual([both]);
    });

    it("S2 solo trip → user_only and partner_only stay empty even when user_score is high", () => {
      const ramen = scoredItem({ [USER]: 0.9 }, "Solo Ramen");
      const buckets = categorize([ramen], "fused", partySolo);
      expect(buckets.user_only).toEqual([]);
      expect(buckets.partner_only).toEqual([]);
      expect(buckets.together).toEqual([ramen]);
    });

    it("S3 old report without match_scores → routes only to together", () => {
      const old = scoredItem(null, "Old");
      const buckets = categorize([old], "fused", partyCouple);
      expect(buckets.together).toEqual([old]);
      expect(buckets.user_only).toEqual([]);
      expect(buckets.partner_only).toEqual([]);
    });

    it("undefined match_scores behaves like null", () => {
      const bare = item({ candidate: { name: "Bare" }, classification: "neutral" });
      const buckets = categorize([bare], "fused", partyCouple);
      expect(buckets.user_only).toEqual([]);
      expect(buckets.partner_only).toEqual([]);
    });

    it("threshold is strict (user_score = 0.6 exactly does NOT route to user_only)", () => {
      const edge = scoredItem({ [USER]: 0.6, [ALICE]: 0.3 }, "Edge");
      const buckets = categorize([edge], "fused", partyCouple);
      expect(buckets.user_only).toEqual([]);
    });

    it("partner_only requires every companion to clear 0.6", () => {
      // alice clears (0.9), bob doesn't (0.5) → does NOT land in partner_only
      const split = scoredItem({ [USER]: 0.1, [ALICE]: 0.9, [BOB]: 0.5 }, "Split");
      const buckets = categorize([split], "fused", partyTrio);
      expect(buckets.partner_only).toEqual([]);
      expect(buckets.together).toEqual([split]);
    });

    it("partner_only fires when EVERY companion clears 0.6", () => {
      const allCompanions = scoredItem(
        { [USER]: 0.2, [ALICE]: 0.8, [BOB]: 0.75 },
        "AllCompanions",
      );
      const buckets = categorize([allCompanions], "fused", partyTrio);
      expect(buckets.partner_only).toEqual([allCompanions]);
    });

    it("party omitted → score-gated tabs stay empty (shared / public path)", () => {
      const ramen = scoredItem({ [USER]: 0.9, [ALICE]: 0.1 }, "Public");
      const buckets = categorize([ramen], "fused");
      expect(buckets.user_only).toEqual([]);
      expect(buckets.partner_only).toEqual([]);
      expect(buckets.together).toEqual([ramen]);
    });
  });
});
