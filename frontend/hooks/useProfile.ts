"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useHasHydrated } from "@/hooks/useHasHydrated";
import { getProfile, updateProfile } from "@/lib/api/profile";
import type { ProfileResponse, ProfileUpdateBody } from "@/lib/schemas/profile";
import { useAuthStore } from "@/store/auth";

const PROFILE_KEY = ["profile"] as const;

/**
 * GET /api/profile — disabled until the auth store rehydrates and a token
 * is present, mirroring `useTrips`.
 */
export function useProfile() {
  const hydrated = useHasHydrated();
  const token = useAuthStore((s) => s.token);
  return useQuery<ProfileResponse>({
    queryKey: PROFILE_KEY,
    queryFn: getProfile,
    enabled: hydrated && !!token,
    staleTime: 30_000,
    retry: false,
  });
}

/**
 * PUT /api/profile — optimistic update with rollback on error (PRD §G5).
 *
 *  onMutate    → snapshot current value, write the optimistic body
 *  onError     → restore the snapshot
 *  onSettled   → revalidate against the server (the server response is the
 *                source of truth — defaults may differ from what the client
 *                sent, e.g. nulls collapsed to absent fields).
 */
export function useUpdateProfile() {
  const qc = useQueryClient();
  return useMutation<ProfileResponse, unknown, ProfileUpdateBody, { previous?: ProfileResponse }>({
    mutationFn: (body) => updateProfile(body),
    onMutate: async (newBody) => {
      await qc.cancelQueries({ queryKey: PROFILE_KEY });
      const previous = qc.getQueryData<ProfileResponse>(PROFILE_KEY);
      // Optimistically write the typed body — it has the same shape as
      // ProfileResponse on every field except for backend-only ones (none
      // in v1 — implicit_preferences is omitted from both).
      qc.setQueryData<ProfileResponse>(PROFILE_KEY, newBody);
      return { previous };
    },
    onError: (_err, _body, ctx) => {
      if (ctx?.previous !== undefined) {
        qc.setQueryData(PROFILE_KEY, ctx.previous);
      }
    },
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: PROFILE_KEY });
    },
  });
}
