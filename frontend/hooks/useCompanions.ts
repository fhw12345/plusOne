"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useHasHydrated } from "@/hooks/useHasHydrated";
import {
  createCompanion,
  deleteCompanion,
  listCompanions,
  updateCompanion,
} from "@/lib/api/companions";
import type {
  CompanionCreateBody,
  CompanionResponse,
  CompanionsListResponse,
  CompanionUpdateBody,
} from "@/lib/schemas/companions";
import { useAuthStore } from "@/store/auth";

const COMPANIONS_KEY = ["companions", "list"] as const;

export function useCompanions() {
  const hydrated = useHasHydrated();
  const token = useAuthStore((s) => s.token);
  return useQuery<CompanionsListResponse>({
    queryKey: COMPANIONS_KEY,
    queryFn: listCompanions,
    enabled: hydrated && !!token,
    staleTime: 30_000,
    retry: false,
  });
}

/**
 * Create / update / delete mutations — NOT optimistic per PRD §G5: the
 * dialog stays open on error and closes only after the server returns 2xx
 * so the user has a single, unambiguous confirmation point.
 */
export function useCreateCompanion() {
  const qc = useQueryClient();
  return useMutation<CompanionResponse, unknown, CompanionCreateBody>({
    mutationFn: (body) => createCompanion(body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: COMPANIONS_KEY });
    },
  });
}

export function useUpdateCompanion() {
  const qc = useQueryClient();
  return useMutation<CompanionResponse, unknown, { id: string; body: CompanionUpdateBody }>({
    mutationFn: ({ id, body }) => updateCompanion(id, body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: COMPANIONS_KEY });
    },
  });
}

export function useDeleteCompanion() {
  const qc = useQueryClient();
  return useMutation<void, unknown, string>({
    mutationFn: (id) => deleteCompanion(id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: COMPANIONS_KEY });
    },
  });
}
