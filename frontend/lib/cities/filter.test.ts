import { describe, expect, it } from "vitest";

import { formatCity, searchCities, type City } from "@/lib/cities";

// A tiny fixture pre-sorted by population desc, just like the real dataset.
const FIXTURE: readonly City[] = [
  { n: "Tokyo", c: "Japan", p: 37_400_000 },
  { n: "Delhi", c: "India", p: 30_290_000 },
  { n: "Paris", c: "France", p: 11_017_000 },
  { n: "Kunming", c: "China", p: 4_710_000 },
  { n: "Kobe", c: "Japan", p: 1_540_000 },
  { n: "Kyoto", c: "Japan", p: 1_460_000 },
  { n: "Krakow", c: "Poland", p: 779_000 },
  { n: "Kingston", c: "Jamaica", p: 580_000 },
  { n: "Karlsruhe", c: "Germany", p: 313_000 },
  { n: "Kyongju", c: "South Korea", p: 264_000 },
];

describe("searchCities", () => {
  it("empty query returns top N by population", () => {
    const r = searchCities("", FIXTURE, 3);
    expect(r.map((c) => c.n)).toEqual(["Tokyo", "Delhi", "Paris"]);
  });

  it("'k' returns cities starting with K, K-prefix only", () => {
    const r = searchCities("k", FIXTURE, 20);
    // No Tokyo (T), no Delhi (D), no Paris (P).
    expect(r.every((c) => c.n.toLowerCase().startsWith("k"))).toBe(true);
    expect(r.map((c) => c.n)).toContain("Kyoto");
    expect(r.map((c) => c.n)).not.toContain("Tokyo");
  });

  it("case-insensitive: 'KY' and 'ky' return same", () => {
    const upper = searchCities("KY", FIXTURE, 20);
    const lower = searchCities("ky", FIXTURE, 20);
    expect(upper.map((c) => c.n)).toEqual(lower.map((c) => c.n));
    expect(lower.map((c) => c.n)).toEqual(["Kyoto", "Kyongju"]);
  });

  it("results ranked by population desc", () => {
    const r = searchCities("k", FIXTURE, 20);
    const pops = r.map((c) => c.p);
    const sorted = [...pops].sort((a, b) => b - a);
    expect(pops).toEqual(sorted);
  });

  it("result count clamped to limit", () => {
    const r = searchCities("k", FIXTURE, 2);
    expect(r).toHaveLength(2);
    // First two K-cities by population: Kunming (4.71M), Kobe (1.54M).
    expect(r.map((c) => c.n)).toEqual(["Kunming", "Kobe"]);
  });

  it("query with no match returns empty array", () => {
    const r = searchCities("zzzzz", FIXTURE, 8);
    expect(r).toEqual([]);
  });

  it("trims surrounding whitespace from query", () => {
    const a = searchCities("  ky  ", FIXTURE, 8);
    const b = searchCities("ky", FIXTURE, 8);
    expect(a).toEqual(b);
  });

  it("does NOT match by country", () => {
    // "Japan" is a country, not a city name — should not pull Tokyo/Kyoto/Kobe.
    const r = searchCities("japan", FIXTURE, 8);
    expect(r).toEqual([]);
  });
});

describe("formatCity", () => {
  it("renders 'Name, Country'", () => {
    expect(formatCity({ n: "Kyoto", c: "Japan", p: 1 })).toBe("Kyoto, Japan");
  });
});
