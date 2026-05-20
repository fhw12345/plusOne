import { describe, expect, it } from "vitest";

import {
  CompanionCreateBody,
  CompanionResponse,
  CompanionsListResponse,
} from "@/lib/schemas/companions";

const VALID_BODY = {
  name: "Anna",
  explicit_preferences: { loves: ["matcha"], hates: ["seafood"] },
  constraints: { dietary: ["vegetarian"], mobility: null, max_walking: null },
};

describe("CompanionCreateBody", () => {
  it("accepts a well-formed body", () => {
    const parsed = CompanionCreateBody.parse(VALID_BODY);
    expect(parsed.name).toBe("Anna");
    expect(parsed.explicit_preferences.loves).toEqual(["matcha"]);
  });

  it("rejects an empty name", () => {
    expect(CompanionCreateBody.safeParse({ ...VALID_BODY, name: "" }).success).toBe(false);
  });

  it("rejects a name over 100 chars", () => {
    expect(CompanionCreateBody.safeParse({ ...VALID_BODY, name: "x".repeat(101) }).success).toBe(
      false,
    );
  });

  it("rejects unknown top-level keys (strict)", () => {
    const result = CompanionCreateBody.safeParse({ ...VALID_BODY, unknown: 1 });
    expect(result.success).toBe(false);
  });

  it("rejects more than 50 loves", () => {
    const loves = Array.from({ length: 51 }, (_, i) => `x${i}`);
    expect(
      CompanionCreateBody.safeParse({
        ...VALID_BODY,
        explicit_preferences: { loves, hates: [] },
      }).success,
    ).toBe(false);
  });

  it("rejects more than 20 dietary entries", () => {
    const dietary = Array.from({ length: 21 }, (_, i) => `x${i}`);
    expect(
      CompanionCreateBody.safeParse({
        ...VALID_BODY,
        constraints: { ...VALID_BODY.constraints, dietary },
      }).success,
    ).toBe(false);
  });

  it("rejects max_walking out of bounds", () => {
    expect(
      CompanionCreateBody.safeParse({
        ...VALID_BODY,
        constraints: { ...VALID_BODY.constraints, max_walking: 101 },
      }).success,
    ).toBe(false);
  });
});

describe("CompanionResponse", () => {
  it("requires an id + timestamps", () => {
    const parsed = CompanionResponse.parse({
      id: "11111111-2222-4333-8444-555555555555",
      ...VALID_BODY,
      created_at: "2026-05-20T14:30:00+00:00",
      updated_at: "2026-05-20T14:30:00+00:00",
    });
    expect(parsed.id).toBe("11111111-2222-4333-8444-555555555555");
  });

  it("rejects a non-uuid id", () => {
    expect(
      CompanionResponse.safeParse({
        id: "not-a-uuid",
        ...VALID_BODY,
        created_at: "2026-05-20T14:30:00+00:00",
        updated_at: "2026-05-20T14:30:00+00:00",
      }).success,
    ).toBe(false);
  });
});

describe("CompanionsListResponse", () => {
  it("accepts an empty list", () => {
    const parsed = CompanionsListResponse.parse({ companions: [] });
    expect(parsed.companions).toEqual([]);
  });

  it("rejects unknown top-level keys", () => {
    expect(CompanionsListResponse.safeParse({ companions: [], extra: 1 }).success).toBe(false);
  });
});
