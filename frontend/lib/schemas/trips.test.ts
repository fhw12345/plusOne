import { describe, it, expect } from "vitest";

import {
  CreateTripBody,
  CreateTripResponse,
  TripDetail,
  TripListItem,
  TripListResponse,
} from "@/lib/schemas/trips";

describe("CreateTripBody", () => {
  it("accepts destination only", () => {
    const parsed = CreateTripBody.parse({ destination: "Tokyo" });
    expect(parsed.destination).toBe("Tokyo");
    expect(parsed.free_text).toBeUndefined();
  });

  it("accepts destination + free_text", () => {
    const parsed = CreateTripBody.parse({ destination: "Tokyo", free_text: "ramen" });
    expect(parsed.free_text).toBe("ramen");
  });

  it("rejects empty destination", () => {
    expect(CreateTripBody.safeParse({ destination: "" }).success).toBe(false);
  });

  it("rejects destination over 200 chars", () => {
    expect(CreateTripBody.safeParse({ destination: "x".repeat(201) }).success).toBe(false);
  });

  it("rejects free_text over 2000 chars", () => {
    expect(
      CreateTripBody.safeParse({ destination: "Tokyo", free_text: "x".repeat(2001) }).success,
    ).toBe(false);
  });

  it("accepts companion_ids as an empty array", () => {
    const parsed = CreateTripBody.parse({ destination: "Tokyo", companion_ids: [] });
    expect(parsed.companion_ids).toEqual([]);
  });

  it("accepts companion_ids with valid uuids", () => {
    const parsed = CreateTripBody.parse({
      destination: "Tokyo",
      companion_ids: [
        "11111111-2222-4333-8444-555555555555",
        "22222222-3333-4444-8555-666666666666",
      ],
    });
    expect(parsed.companion_ids?.length).toBe(2);
  });

  it("rejects non-uuid entries in companion_ids", () => {
    expect(
      CreateTripBody.safeParse({
        destination: "Tokyo",
        companion_ids: ["not-a-uuid"],
      }).success,
    ).toBe(false);
  });

  it("rejects > 50 companion_ids", () => {
    const companion_ids = Array.from(
      { length: 51 },
      // crank out 51 valid uuids
      (_, i) => `11111111-2222-4333-8444-${(555555555555 + i).toString().padStart(12, "0")}`,
    );
    expect(CreateTripBody.safeParse({ destination: "Tokyo", companion_ids }).success).toBe(false);
  });

  // === Batch-2o: dates + budget ===========================================

  it("accepts full payload with dates + budget + currency", () => {
    const parsed = CreateTripBody.parse({
      destination: "tokyo",
      date_start: "2026-10-12T00:00:00Z",
      date_end: "2026-10-19T00:00:00Z",
      budget_amount: 2500,
      budget_currency: "USD",
    });
    expect(parsed.budget_amount).toBe(2500);
    expect(parsed.budget_currency).toBe("USD");
  });

  it("rejects date_end before date_start with voice copy on date_end path", () => {
    const result = CreateTripBody.safeParse({
      destination: "tokyo",
      date_start: "2026-11-05T00:00:00Z",
      date_end: "2026-11-02T00:00:00Z",
    });
    expect(result.success).toBe(false);
    if (!result.success) {
      const issue = result.error.issues.find((i) => i.path.join(".") === "date_end");
      expect(issue?.message).toBe("the end is before the start. flip them?");
    }
  });

  it("accepts equal date_start and date_end", () => {
    const parsed = CreateTripBody.parse({
      destination: "tokyo",
      date_start: "2026-10-12T00:00:00Z",
      date_end: "2026-10-12T00:00:00Z",
    });
    expect(parsed.date_start).toBe(parsed.date_end);
  });

  it("rejects unknown currency", () => {
    expect(CreateTripBody.safeParse({ destination: "tokyo", budget_currency: "ZZZ" }).success).toBe(
      false,
    );
  });

  it("rejects negative budget with voice copy", () => {
    const result = CreateTripBody.safeParse({ destination: "tokyo", budget_amount: -5 });
    expect(result.success).toBe(false);
    if (!result.success) {
      const issue = result.error.issues.find((i) => i.path.join(".") === "budget_amount");
      expect(issue?.message).toBe("budget can't be negative.");
    }
  });

  it("rejects non-integer budget with voice copy", () => {
    const result = CreateTripBody.safeParse({ destination: "tokyo", budget_amount: 2.5 });
    expect(result.success).toBe(false);
    if (!result.success) {
      const issue = result.error.issues.find((i) => i.path.join(".") === "budget_amount");
      expect(issue?.message).toBe("whole numbers only.");
    }
  });

  it("accepts zero budget", () => {
    const parsed = CreateTripBody.parse({ destination: "tokyo", budget_amount: 0 });
    expect(parsed.budget_amount).toBe(0);
  });

  it("accepts missing currency when amount is also missing", () => {
    const parsed = CreateTripBody.parse({ destination: "tokyo" });
    expect(parsed.budget_amount).toBeUndefined();
    expect(parsed.budget_currency).toBeUndefined();
  });
});

describe("CreateTripResponse", () => {
  it("parses a valid uuid response", () => {
    const parsed = CreateTripResponse.parse({
      trip_id: "11111111-2222-4333-8444-555555555555",
      status: "pending",
    });
    expect(parsed.trip_id).toBe("11111111-2222-4333-8444-555555555555");
  });

  it("rejects non-uuid trip_id", () => {
    expect(CreateTripResponse.safeParse({ trip_id: "not-a-uuid", status: "pending" }).success).toBe(
      false,
    );
  });
});

describe("TripDetail", () => {
  it("accepts null latest_report_id + content", () => {
    const parsed = TripDetail.parse({
      trip_id: "11111111-2222-4333-8444-555555555555",
      destination: "Tokyo",
      status: "pending",
      latest_report_id: null,
      content: null,
    });
    expect(parsed.status).toBe("pending");
    expect(parsed.content).toBeNull();
  });

  it("accepts populated content with passthrough items", () => {
    const parsed = TripDetail.parse({
      trip_id: "11111111-2222-4333-8444-555555555555",
      destination: "Tokyo",
      status: "complete",
      latest_report_id: "11111111-2222-4333-8444-666666666666",
      content: { items: [{ name: "shop a", whatever: 1 }] },
    });
    expect(parsed.content?.items.length).toBe(1);
  });

  it("rejects an unknown status enum", () => {
    expect(
      TripDetail.safeParse({
        trip_id: "11111111-2222-4333-8444-555555555555",
        destination: "Tokyo",
        status: "bogus",
        latest_report_id: null,
        content: null,
      }).success,
    ).toBe(false);
  });
});

describe("TripListItem", () => {
  const valid = {
    trip_id: "11111111-2222-4333-8444-555555555555",
    destination: "Tokyo",
    status: "complete",
    created_at: "2026-05-20T14:30:00+00:00",
    latest_report_id: "11111111-2222-4333-8444-666666666666",
    has_report: true,
  };

  it("parses a valid payload", () => {
    const parsed = TripListItem.parse(valid);
    expect(parsed.destination).toBe("Tokyo");
    expect(parsed.has_report).toBe(true);
  });

  it("accepts null latest_report_id", () => {
    const parsed = TripListItem.parse({
      ...valid,
      latest_report_id: null,
      has_report: false,
    });
    expect(parsed.latest_report_id).toBeNull();
  });

  it("rejects missing has_report", () => {
    const { has_report: _omit, ...rest } = valid;
    void _omit;
    expect(TripListItem.safeParse(rest).success).toBe(false);
  });

  it("rejects non-ISO created_at", () => {
    expect(TripListItem.safeParse({ ...valid, created_at: "not-a-date" }).success).toBe(false);
  });
});

describe("TripListResponse", () => {
  it("accepts next_cursor: null", () => {
    const parsed = TripListResponse.parse({ trips: [], next_cursor: null });
    expect(parsed.next_cursor).toBeNull();
    expect(parsed.trips).toEqual([]);
  });

  it("accepts a populated cursor + trips", () => {
    const parsed = TripListResponse.parse({
      trips: [
        {
          trip_id: "11111111-2222-4333-8444-555555555555",
          destination: "Tokyo",
          status: "pending",
          created_at: "2026-05-20T14:30:00+00:00",
          latest_report_id: null,
          has_report: false,
        },
      ],
      next_cursor: "abc123",
    });
    expect(parsed.next_cursor).toBe("abc123");
    expect(parsed.trips).toHaveLength(1);
  });
});

describe("TripContent backwards compatibility (batch-2p + batch-2q)", () => {
  it("accepts the legacy bare-array translations shape and normalises to object form", async () => {
    const { TripContent } = await import("@/lib/schemas/trips");
    const parsed = TripContent.parse({
      items: [{ candidate: { name: "x" } }],
      translations: {
        zh: [{ candidate: { name: "翻译" } }],
      },
    });
    expect(parsed.translations?.zh).toEqual({ items: [{ candidate: { name: "翻译" } }] });
  });

  it("accepts the new object translations shape with tl_dr", async () => {
    const { TripContent } = await import("@/lib/schemas/trips");
    const parsed = TripContent.parse({
      items: [{ candidate: { name: "x" } }],
      tl_dr: "kyoto's still a place where good tea matters.",
      translations: {
        en: { items: [{ candidate: { name: "x-en" } }], tl_dr: "english tl_dr" },
      },
    });
    expect(parsed.tl_dr).toContain("kyoto");
    expect(parsed.translations?.en?.tl_dr).toBe("english tl_dr");
  });

  it("accepts TripDetail with optional party (batch-2p)", async () => {
    const { TripDetail } = await import("@/lib/schemas/trips");
    const parsed = TripDetail.parse({
      trip_id: "11111111-2222-4333-8444-555555555555",
      destination: "Tokyo",
      status: "complete",
      latest_report_id: null,
      content: null,
      party: {
        user_id: "11111111-2222-4333-8444-666666666666",
        companion_ids: ["22222222-3333-4444-8555-777777777777"],
      },
    });
    expect(parsed.party?.companion_ids).toHaveLength(1);
  });

  it("accepts TripDetail without party (pre-2p shape)", async () => {
    const { TripDetail } = await import("@/lib/schemas/trips");
    const parsed = TripDetail.parse({
      trip_id: "11111111-2222-4333-8444-555555555555",
      destination: "Tokyo",
      status: "complete",
      latest_report_id: null,
      content: null,
    });
    expect(parsed.party).toBeUndefined();
  });
});
