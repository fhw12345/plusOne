import { describe, expect, it } from "vitest";

import {
  Demographics,
  ExplicitPreferences,
  ProfileResponse,
  ProfileUpdateBody,
  TravelStyle,
  VisitedCity,
} from "@/lib/schemas/profile";

const EMPTY_PROFILE = {
  demographics: { age_range: null, language: null },
  travel_style: { budget_sensitivity: null, pace: null, comfort: null },
  explicit_preferences: { loves: [], hates: [] },
  visited_cities: [],
};

describe("Demographics / TravelStyle", () => {
  it("accepts a fully populated demographics", () => {
    const parsed = Demographics.parse({ age_range: "30-39", language: "en" });
    expect(parsed.age_range).toBe("30-39");
  });

  it("accepts nulls / omissions", () => {
    expect(Demographics.parse({}).age_range).toBeUndefined();
    expect(Demographics.parse({ age_range: null }).age_range).toBeNull();
  });

  it("rejects unknown keys (strict)", () => {
    expect(Demographics.safeParse({ age_range: "x", unknown: 1 }).success).toBe(false);
    expect(TravelStyle.safeParse({ pace: "fast", unknown: 1 }).success).toBe(false);
  });
});

describe("ExplicitPreferences", () => {
  it("requires loves + hates arrays", () => {
    expect(ExplicitPreferences.safeParse({}).success).toBe(false);
    expect(ExplicitPreferences.parse({ loves: [], hates: [] }).loves).toEqual([]);
  });

  it("rejects > 50 entries", () => {
    const loves = Array.from({ length: 51 }, (_, i) => `x${i}`);
    expect(ExplicitPreferences.safeParse({ loves, hates: [] }).success).toBe(false);
  });
});

describe("VisitedCity", () => {
  it("accepts a minimal {city, year}", () => {
    const parsed = VisitedCity.parse({ city: "Tokyo", year: 2024 });
    expect(parsed.city).toBe("Tokyo");
    expect(parsed.rating).toBeUndefined();
  });

  it("rejects year out of bounds", () => {
    expect(VisitedCity.safeParse({ city: "Tokyo", year: 1899 }).success).toBe(false);
    expect(VisitedCity.safeParse({ city: "Tokyo", year: 2101 }).success).toBe(false);
  });

  it("rejects rating out of bounds", () => {
    expect(VisitedCity.safeParse({ city: "Tokyo", year: 2024, rating: 0 }).success).toBe(false);
    expect(VisitedCity.safeParse({ city: "Tokyo", year: 2024, rating: 6 }).success).toBe(false);
  });
});

describe("ProfileResponse / ProfileUpdateBody", () => {
  it("ProfileResponse accepts an empty-default object", () => {
    const parsed = ProfileResponse.parse(EMPTY_PROFILE);
    expect(parsed.visited_cities).toEqual([]);
  });

  it("ProfileUpdateBody rejects unknown top-level keys (no implicit_preferences leak)", () => {
    const result = ProfileUpdateBody.safeParse({
      ...EMPTY_PROFILE,
      implicit_preferences: [],
    });
    expect(result.success).toBe(false);
  });

  it("ProfileUpdateBody rejects > 100 visited_cities", () => {
    const visited_cities = Array.from({ length: 101 }, (_, i) => ({
      city: `c${i}`,
      year: 2024,
    }));
    expect(ProfileUpdateBody.safeParse({ ...EMPTY_PROFILE, visited_cities }).success).toBe(false);
  });
});
