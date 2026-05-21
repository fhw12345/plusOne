import { describe, expect, it, vi } from "vitest";
import { renderToString } from "react-dom/server";

import { ChipInput } from "@/components/profile/ChipInput";

describe("ChipInput (SSR markup)", () => {
  it("renders each value as a chip with a remove button", () => {
    const html = renderToString(
      <ChipInput value={["ramen", "kissaten"]} onChange={vi.fn()} ariaLabel="Loves" />,
    );
    expect(html).toContain("ramen");
    expect(html).toContain("kissaten");
    expect(html).toContain(`aria-label="remove ramen"`);
    expect(html).toContain(`aria-label="remove kissaten"`);
  });

  it("renders the input with the placeholder when below the cap", () => {
    const html = renderToString(
      <ChipInput value={[]} onChange={vi.fn()} ariaLabel="Loves" placeholder="Add love" />,
    );
    expect(html).toContain(`placeholder="Add love"`);
  });

  it("switches to a 'Maximum N reached' placeholder at the cap", () => {
    const value = Array.from({ length: 3 }, (_, i) => `v${i}`);
    const html = renderToString(
      <ChipInput value={value} onChange={vi.fn()} ariaLabel="Loves" max={3} />,
    );
    // Voice rule (VOICE.md): placeholder uses lowercase scrapbook phrasing
    // when the chip cap is hit, not "Maximum N reached".
    expect(html).toContain("that&#x27;s 3");
    expect(html).toContain("delete one to add more");
    // Disabled input at cap
    expect(html).toContain("disabled");
  });
});
