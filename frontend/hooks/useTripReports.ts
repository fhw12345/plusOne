"use client";

import { useQuery } from "@tanstack/react-query";

import { useHasHydrated } from "@/hooks/useHasHydrated";
import { listTripReports } from "@/lib/api/trips";
import { useAuthStore } from "@/store/auth";

/**
 * Paginated isn't needed for revisions — a trip rarely has more than a
 * handful — so this is a flat `useQuery` over the chronological list
 * endpoint. Refetched after each refine completes (the page-level
 * `trip_complete` SSE event triggers `qc.invalidateQueries`).
 */
export function useTripReports(tripId: string | null) {
  const hydrated = useHasHydrated();
  const token = useAuthStore((s) => s.token);

  return useQuery({
    queryKey: ["trip-reports", tripId],
    queryFn: () => listTripReports(tripId as string),
    enabled: hydrated && !!token && !!tripId,
    staleTime: 30_000,
    retry: false,
  });
}
