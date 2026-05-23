import { describe, expect, it } from "vitest";
import { renderToString } from "react-dom/server";

import { ItemCard } from "@/components/trips/ItemCard";
import type { JoinedItem } from "@/lib/schemas/trips";

function mkItem(): JoinedItem {
  return {
    candidate: { name: "Test Spot", area: null, style: null, rationale: "" },
    classification: "local_gem",
    classification_en: "local_gem",
    classification_zh: "neutral",
    confidence: 0.8,
    evidence: [
      { source: "reddit", url: "https://reddit.com/r/x/1", snippet: "rdt" },
      { source: "xiaohongshu", url: "https://xiaohongshu.com/2", snippet: "xhs" },
      { source: "foursquare", url: "https://foursquare.com/v/3", snippet: "fsq" },
    ],
    summary: "summary",
  } as JoinedItem;
}

describe("ItemCard perspective wiring (PRD batch-2r §4.2d)", () => {
  describe("verdict via resolveClassification", () => {
    it("fused: shows verdict from fused classification", () => {
      const html = renderToString(<ItemCard item={mkItem()} perspective="fused" />);
      // local_gem -> "this one ★"
      expect(html).toContain("this one");
    });

    it("zh: shows verdict from classification_zh (neutral -> okay-ish)", () => {
      const html = renderToString(<ItemCard item={mkItem()} perspective="zh" />);
      expect(html).toContain("okay-ish");
      expect(html).not.toContain("this one");
    });

    it("en: shows verdict from classification_en (local_gem -> this one ★)", () => {
      const html = renderToString(<ItemCard item={mkItem()} perspective="en" />);
      expect(html).toContain("this one");
    });

    it("pre-2i item (no per-side fields) falls back to fused under every perspective", () => {
      const old = {
        candidate: { name: "Old" },
        classification: "local_gem",
        evidence: [],
      } as unknown as JoinedItem;
      for (const p of ["fused", "zh", "en"] as const) {
        const html = renderToString(<ItemCard item={old} perspective={p} />);
        expect(html).toContain("this one");
      }
    });
  });

  describe("evidence filter by perspective", () => {
    it("fused: keeps all evidence sources", () => {
      const html = renderToString(<ItemCard item={mkItem()} perspective="fused" />);
      expect(html).toContain("reddit.com");
      expect(html).toContain("xiaohongshu.com");
      expect(html).toContain("foursquare.com");
    });

    it("en: keeps reddit + foursquare, hides xiaohongshu", () => {
      const html = renderToString(<ItemCard item={mkItem()} perspective="en" />);
      expect(html).toContain("reddit.com");
      expect(html).toContain("foursquare.com");
      expect(html).not.toContain("xiaohongshu.com");
    });

    it("zh: keeps xiaohongshu + foursquare, hides reddit", () => {
      const html = renderToString(<ItemCard item={mkItem()} perspective="zh" />);
      expect(html).toContain("xiaohongshu.com");
      expect(html).toContain("foursquare.com");
      expect(html).not.toContain("reddit.com");
    });

    it("evidence count badge reflects filtered count under en", () => {
      // Full evidence is 3 sources; under en the xhs entry is dropped -> 2.
      const html = renderToString(<ItemCard item={mkItem()} perspective="en" />);
      // The badge strip shows `sources 2` for the filtered count.
      expect(html).toMatch(/sources[^0-9]*2/);
    });

    it("defaults to fused when perspective prop omitted (back-compat)", () => {
      const html = renderToString(<ItemCard item={mkItem()} />);
      expect(html).toContain("xiaohongshu.com");
      expect(html).toContain("reddit.com");
    });
  });
});

describe("ItemCard match line (PRD batch-2p §4.2)", () => {
  const USER = "11111111-2222-4333-8444-555555555555";
  const ALICE = "22222222-3333-4444-8555-666666666666";

  function scored(scores: Record<string, number> | null): JoinedItem {
    return {
      candidate: { name: "Scored", area: null, style: null, rationale: "" },
      classification: "local_gem",
      classification_en: "local_gem",
      classification_zh: "local_gem",
      confidence: 0.8,
      evidence: [],
      summary: "",
      match_scores: scores,
    } as unknown as JoinedItem;
  }

  it("renders 'match  you: 0.8 · alice: 0.3' in the expanded body", () => {
    const html = renderToString(
      <ItemCard
        item={scored({ [USER]: 0.83, [ALICE]: 0.3 })}
        party={{ user_id: USER, companion_ids: [ALICE] }}
        partyNames={{ [USER]: "you", [ALICE]: "alice" }}
      />,
    );
    // Body is hidden in collapsed state but still serialized to HTML.
    expect(html).toMatch(/data-testid="match-line"/);
    expect(html).toContain("you: 0.8");
    expect(html).toContain("alice: 0.3");
    // Lowercase / scrapbook voice. We strip HTML tags + attributes from
    // the match-line slice and assert the visible TEXT (not inline style
    // strings, which may legitimately contain non-lowercase chars) is
    // all-lowercase and free of exclamation.
    const matchSlice = html.split('data-testid="match-line"')[1]?.split("</p>")[0] ?? "";
    const visibleText = matchSlice.replace(/<[^>]+>/g, "").replace(/^[^>]*>/, "");
    expect(visibleText).not.toContain("!");
    expect(visibleText).toEqual(visibleText.toLowerCase());
  });

  it("rounds scores to one decimal place", () => {
    const html = renderToString(
      <ItemCard
        item={scored({ [USER]: 0.5, [ALICE]: 0.83 })}
        party={{ user_id: USER, companion_ids: [ALICE] }}
        partyNames={{ [USER]: "you", [ALICE]: "alice" }}
      />,
    );
    expect(html).toContain("you: 0.5");
    expect(html).toContain("alice: 0.8");
  });

  it("hides the match line when match_scores is null", () => {
    const html = renderToString(
      <ItemCard
        item={scored(null)}
        party={{ user_id: USER, companion_ids: [ALICE] }}
        partyNames={{ [USER]: "you", [ALICE]: "alice" }}
      />,
    );
    expect(html).not.toMatch(/data-testid="match-line"/);
  });

  it("hides the match line when party has no companions (solo trip)", () => {
    const html = renderToString(
      <ItemCard
        item={scored({ [USER]: 0.9 })}
        party={{ user_id: USER, companion_ids: [] }}
        partyNames={{ [USER]: "you" }}
      />,
    );
    expect(html).not.toMatch(/data-testid="match-line"/);
  });

  it("hides the match line when party is absent (public / shared report)", () => {
    const html = renderToString(<ItemCard item={scored({ [USER]: 0.9 })} />);
    expect(html).not.toMatch(/data-testid="match-line"/);
  });

  it("lowercases companion names from the partyNames map", () => {
    const html = renderToString(
      <ItemCard
        item={scored({ [USER]: 0.8, [ALICE]: 0.3 })}
        party={{ user_id: USER, companion_ids: [ALICE] }}
        partyNames={{ [USER]: "you", [ALICE]: "Alice" }}
      />,
    );
    expect(html).toContain("alice: 0.3");
    expect(html).not.toContain("Alice:");
  });
});
