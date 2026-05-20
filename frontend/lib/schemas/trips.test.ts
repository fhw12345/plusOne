import { describe, it, expect } from "vitest";

import { CreateTripBody, CreateTripResponse, TripDetail } from "@/lib/schemas/trips";

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
