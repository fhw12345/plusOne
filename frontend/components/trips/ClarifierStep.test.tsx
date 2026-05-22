import { describe, expect, it, vi } from "vitest";
import { renderToString } from "react-dom/server";

// next/navigation stub — repo has no jsdom; we never actually navigate.
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: () => {}, replace: () => {}, refresh: () => {} }),
}));

import { ClarifierStep } from "@/components/trips/ClarifierStep";

const TRIP_ID = "11111111-2222-4333-8444-555555555555";

describe("ClarifierStep (SSR markup) — batch-2t", () => {
  it("renders the scrapbook heading + hint copy", () => {
    const html = renderToString(
      <ClarifierStep
        tripId={TRIP_ID}
        questions={[
          { id: "q1", text: "fixed dates or flexible?" },
          { id: "q2", text: "okay with bus / metro / both?" },
        ]}
      />,
    );
    expect(html).toContain("before i go");
    expect(html).toContain("a couple of quick checks. one-liners fine.");
  });

  it("uses singular hint when only one question", () => {
    const html = renderToString(
      <ClarifierStep
        tripId={TRIP_ID}
        questions={[{ id: "q1", text: "fixed dates or flexible?" }]}
      />,
    );
    expect(html).toContain("a quick check. one-liners fine.");
  });

  it("renders one textarea per question, labeled with the LLM text", () => {
    const html = renderToString(
      <ClarifierStep
        tripId={TRIP_ID}
        questions={[
          { id: "q1", text: "fixed dates or flexible?" },
          { id: "q2", text: "okay with bus / metro / both?" },
          { id: "q3", text: "any cuisines you've already ruled out?" },
        ]}
      />,
    );
    expect(html).toContain('id="clar-q1"');
    expect(html).toContain('id="clar-q2"');
    expect(html).toContain('id="clar-q3"');
    expect(html).toContain("fixed dates or flexible?");
    expect(html).toContain("okay with bus / metro / both?");
    // Render uses the unicode apostrophe so SSR markup matches.
    expect(html).toContain("any cuisines you");
    // Three textareas total.
    expect(html.match(/<textarea/g)?.length).toBe(3);
  });

  it("renders the primary `go look` button and `skip these` link copy", () => {
    const html = renderToString(
      <ClarifierStep
        tripId={TRIP_ID}
        questions={[{ id: "q1", text: "fixed dates or flexible?" }]}
      />,
    );
    expect(html).toContain("go look");
    expect(html).toContain("skip these");
  });

  it("does NOT render banned phrases or title-case labels", () => {
    const html = renderToString(
      <ClarifierStep
        tripId={TRIP_ID}
        questions={[{ id: "q1", text: "fixed dates or flexible?" }]}
      />,
    );
    // Voice rules: no "Submitting", "Loading", "Please", "Sorry", exclamations
    // in our copy. (Question text comes from the LLM, not asserted here.)
    expect(html).not.toMatch(/Submitting/);
    expect(html).not.toMatch(/Loading/);
    expect(html).not.toMatch(/Please/);
    expect(html).not.toMatch(/Sorry/);
    expect(html).not.toMatch(/Powered by AI/);
  });
});
