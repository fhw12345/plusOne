"use client";

import { useQuery } from "@tanstack/react-query";

import { useHasHydrated } from "@/hooks/useHasHydrated";
import { getTrip } from "@/lib/api/trips";
import { useAuthStore } from "@/store/auth";

export function useTrip(tripId: string | null) {
  const hydrated = useHasHydrated();
  const token = useAuthStore((s) => s.token);

  return useQuery({
    queryKey: ["trip", tripId],
    queryFn: () => getTrip(tripId as string),
    enabled: hydrated && !!token && !!tripId,
    staleTime: 30_000,
    retry: false,
  });
}
