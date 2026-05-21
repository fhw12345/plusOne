import { describe, expect, it, vi } from "vitest";
import { renderToString } from "react-dom/server";

import { CompanionCard } from "@/components/companions/CompanionCard";
import type { CompanionResponse } from "@/lib/schemas/companions";

const SAMPLE: CompanionResponse = {
  id: "11111111-2222-4333-8444-555555555555",
  name: "Anna",
  explicit_preferences: {
    loves: ["matcha", "kissaten", "vinyl shops", "extra1", "extra2"],
    hates: ["seafood"],
  },
  constraints: {
    dietary: ["vegetarian", "no-pork"],
    mobility: "limited stairs",
    max_walking: 8,
  },
  created_at: "2026-05-20T14:30:00+00:00",
  updated_at: "2026-05-20T14:30:00+00:00",
};

describe("CompanionCard (SSR markup)", () => {
  it("renders the companion name", () => {
    const html = renderToString(
      <CompanionCard companion={SAMPLE} onEdit={vi.fn()} onDelete={vi.fn()} />,
    );
    expect(html).toContain("Anna");
  });

  it("renders the top-3 loves and truncates the rest with a +N indicator", () => {
    const html = renderToString(
      <CompanionCard companion={SAMPLE} onEdit={vi.fn()} onDelete={vi.fn()} />,
    );
    expect(html).toContain("matcha");
    expect(html).toContain("kissaten");
    expect(html).toContain("vinyl shops");
    // React SSR injects an HTML comment marker between adjacent text nodes
    // for hydration: `+<!-- -->2`. Strip comments before asserting.
    expect(html.replace(/<!--[\s\S]*?-->/g, "")).toContain("+2");
    // Beyond-top items must not be rendered as chips
    expect(html).not.toContain("extra1");
  });

  it("renders hates + dietary + mobility summary", () => {
    const html = renderToString(
      <CompanionCard companion={SAMPLE} onEdit={vi.fn()} onDelete={vi.fn()} />,
    );
    const clean = html.replace(/<!--[\s\S]*?-->/g, "");
    expect(clean).toContain("seafood");
    expect(clean).toContain("vegetarian");
    expect(clean).toContain("limited stairs");
    expect(clean).toContain("8 km/day");
  });

  it("renders edit + remove controls (lowercase, scrapbook voice)", () => {
    const html = renderToString(
      <CompanionCard companion={SAMPLE} onEdit={vi.fn()} onDelete={vi.fn()} />,
    );
    expect(html).toContain("edit");
    expect(html).toContain("remove");
  });
});
