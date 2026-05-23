// Leading-substring city matcher for the destination combobox.
//
// The `cities` array is expected to be pre-sorted by population descending
// (built by `scripts/build-cities.ts`), so early-exiting at `limit` matches
// is correct — the first N hits ARE the top-N by population.

export type City = {
  /** name, e.g. "Kyoto" */
  n: string;
  /** country, e.g. "Japan" */
  c: string;
  /** population — used for ranking only, not displayed */
  p: number;
};

/**
 * Returns up to `limit` cities whose name begins with `query` (case-insensitive).
 * Empty query returns the top `limit` by population (the head of the array).
 *
 * Whitespace is trimmed from `query`. Matching is leading-substring on the
 * city `name` only — does NOT match on country.
 */
export function searchCities(query: string, cities: readonly City[], limit = 8): City[] {
  const q = query.trim().toLowerCase();
  if (q === "") {
    return cities.slice(0, limit);
  }
  const out: City[] = [];
  for (const city of cities) {
    if (city.n.toLowerCase().startsWith(q)) {
      out.push(city);
      if (out.length >= limit) break;
    }
  }
  return out;
}

/** Display format: "Kyoto, Japan". */
export function formatCity(c: City): string {
  return `${c.n}, ${c.c}`;
}
