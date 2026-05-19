"use client";

import { useQuery } from "@tanstack/react-query";

import { useHasHydrated } from "@/hooks/useHasHydrated";
import { me } from "@/lib/api/auth";
import { useAuthStore } from "@/store/auth";

/**
 * Wraps `GET /api/auth/me` in a TanStack Query. Disabled until the auth
 * store has rehydrated AND a token is present — so SSR / pre-hydration
 * paints never trigger an unnecessary request, and signed-out users never
 * hit a guaranteed-401 endpoint.
 */
export function useCurrentUser() {
  const hydrated = useHasHydrated();
  const token = useAuthStore((s) => s.token);

  return useQuery({
    queryKey: ["auth", "me"],
    queryFn: me,
    enabled: hydrated && !!token,
    staleTime: 60_000,
    retry: false,
  });
}
