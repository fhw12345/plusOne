import { describe, expect, it } from "vitest";

import type { JoinedItem } from "@/lib/schemas/trips";
import { resolveClassification } from "./resolveClassification";

function item(over: Record<string, unknown> = {}): JoinedItem {
  return {
    candidate: { name: "x" },
    ...over,
  } as JoinedItem;
}

describe("resolveClassification", () => {
  describe("fused perspective", () => {
    it("returns fused classification when present", () => {
      expect(
        resolveClassification(
          item({ classification: "local_gem", classification_en: "neutral", classification_zh: "tourist_trap" }),
          "fused",
        ),
      ).toBe("local_gem");
    });

    it("returns undefined when fused absent", () => {
      expect(
        resolveClassification(
          item({ classification_en: "local_gem", classification_zh: "local_gem" }),
          "fused",
        ),
      ).toBeUndefined();
    });
  });

  describe("zh perspective", () => {
    it("returns classification_zh when present", () => {
      expect(
        resolveClassification(
          item({ classification: "local_gem", classification_zh: "neutral" }),
          "zh",
        ),
      ).toBe("neutral");
    });

    it("falls back to fused when classification_zh is null", () => {
      expect(
        resolveClassification(
          item({ classification: "local_gem", classification_zh: null }),
          "zh",
        ),
      ).toBe("local_gem");
    });

    it("falls back to fused when classification_zh is missing (old reports)", () => {
      expect(
        resolveClassification(item({ classification: "tourist_trap" }), "zh"),
      ).toBe("tourist_trap");
    });

    it("returns undefined when both per-side and fused absent", () => {
      expect(resolveClassification(item({}), "zh")).toBeUndefined();
    });
  });

  describe("en perspective", () => {
    it("returns classification_en when present", () => {
      expect(
        resolveClassification(
          item({ classification: "neutral", classification_en: "local_gem" }),
          "en",
        ),
      ).toBe("local_gem");
    });

    it("falls back to fused when classification_en is null", () => {
      expect(
        resolveClassification(
          item({ classification: "tourist_trap", classification_en: null }),
          "en",
        ),
      ).toBe("tourist_trap");
    });

    it("falls back to fused when classification_en is missing (old reports)", () => {
      expect(
        resolveClassification(item({ classification: "local_gem" }), "en"),
      ).toBe("local_gem");
    });

    it("returns undefined when both per-side and fused absent", () => {
      expect(resolveClassification(item({}), "en")).toBeUndefined();
    });
  });

  it("preserves insufficient as a real per-side outcome (not fallback)", () => {
    // PRD §8 Q2: insufficient is a real outcome, only null triggers fallback.
    expect(
      resolveClassification(
        item({ classification: "local_gem", classification_zh: "insufficient" }),
        "zh",
      ),
    ).toBe("insufficient");
  });
});
