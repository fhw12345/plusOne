"use client";

import { useInfiniteQuery } from "@tanstack/react-query";

import { useHasHydrated } from "@/hooks/useHasHydrated";
import { listTrips } from "@/lib/api/trips";
import type { TripListResponse } from "@/lib/schemas/trips";
import { useAuthStore } from "@/store/auth";

/**
 * Paginated trip list — wraps `useInfiniteQuery` over `listTrips`.
 *
 * Disabled until the auth store rehydrates + a token is present so the
 * first request always carries the JWT.
 *
 * Snapshot semantics: the cursor is anchored to the first-page tuple
 * (created_at, id), so trips created mid-pagination won't appear on
 * subsequent pages — user must refresh. Documented in PRD §5.3.
 */
export function useTrips() {
  const hydrated = useHasHydrated();
  const token = useAuthStore((s) => s.token);

  return useInfiniteQuery<TripListResponse>({
    queryKey: ["trips", "list"],
    queryFn: ({ pageParam }) =>
      listTrips({ limit: 20, cursor: (pageParam as string | undefined) ?? null }),
    initialPageParam: undefined,
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    enabled: hydrated && !!token,
    staleTime: 30_000,
    retry: false,
  });
}
