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
