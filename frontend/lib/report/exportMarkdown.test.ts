import { describe, expect, it } from "vitest";

import { reportToMarkdown } from "@/lib/report/exportMarkdown";
import type { TripDetail } from "@/lib/schemas/trips";

function makeTrip(overrides: Partial<TripDetail> = {}): TripDetail {
  return {
    trip_id: "11111111-2222-4333-8444-555555555555",
    destination: "Tokyo",
    status: "complete",
    latest_report_id: "11111111-2222-4333-8444-666666666666",
    content: {
      items: [
        {
          classification: "local_gem",
          candidate: { name: "Ichiran Ramen" },
          summary: "Late-night counter ramen with privacy booths",
          evidence: [
            { source: "reddit", url: "https://reddit.com/r/x" },
            { source: "xiaohongshu", url: "https://xhs.com/y" },
          ],
        },
      ],
    },
    ...overrides,
  };
}

describe("reportToMarkdown", () => {
  it("includes the destination heading and a Local Gems section with source links", () => {
    const md = reportToMarkdown(makeTrip());

    expect(md).toContain("# Trip to Tokyo");
    expect(md).toContain("## Local Gems");
    expect(md).toContain("**Ichiran Ramen**");
    expect(md).toContain("Late-night counter ramen with privacy booths");
    expect(md).toContain("[reddit](https://reddit.com/r/x)");
    expect(md).toContain("[xiaohongshu](https://xhs.com/y)");
  });

  it("escapes pipe characters in candidate names so they don't break tables", () => {
    const md = reportToMarkdown(
      makeTrip({
        content: {
          items: [
            {
              classification: "local_gem",
              candidate: { name: "Bar | Hidden" },
              summary: "A bar with | in its name",
            },
          ],
        },
      }),
    );

    expect(md).toContain("**Bar \\| Hidden**");
    expect(md).toContain("A bar with \\| in its name");
  });
});
