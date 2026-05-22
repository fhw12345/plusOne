"use client";

import * as React from "react";

import type { City } from "@/lib/cities";

export type CityIndexState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "ready"; cities: readonly City[] }
  | { status: "error"; error: Error };

/**
 * Lazy-load the static city dataset. Singleton across the page session —
 * re-mounting the consumer never re-fetches.
 *
 * Returns:
 *   { status: "loading" }                 while the fetch is in flight
 *   { status: "ready", cities: [...] }    on success
 *   { status: "error", error }            on fetch/parse failure
 *
 * Consumers (e.g. DestinationCombobox) treat "loading" and "error" the same
 * way: the input still accepts text, the dropdown just doesn't open. There
 * is no visible spinner or error toast — staying out of the way is the point.
 */
let cached: Promise<readonly City[]> | null = null;

function loadCities(): Promise<readonly City[]> {
  if (cached) return cached;
  cached = fetch("/data/cities-15k.json", { credentials: "omit" })
    .then((res) => {
      if (!res.ok) throw new Error(`cities fetch ${res.status}`);
      return res.json() as Promise<readonly City[]>;
    })
    .catch((err) => {
      // Reset so a re-mount can retry once next-tick (rare; we don't
      // surface this to the user, the combobox silently degrades).
      cached = null;
      throw err instanceof Error ? err : new Error(String(err));
    });
  return cached;
}

export function useCityIndex(): CityIndexState {
  const [state, setState] = React.useState<CityIndexState>(() => ({
    status: "loading",
  }));

  React.useEffect(() => {
    let alive = true;
    loadCities().then(
      (cities) => {
        if (alive) setState({ status: "ready", cities });
      },
      (error: Error) => {
        if (alive) setState({ status: "error", error });
      },
    );
    return () => {
      alive = false;
    };
  }, []);

  return state;
}

/** Testing only — drop the module-level cache. */
export function __resetCityIndexCacheForTests(): void {
  cached = null;
}
