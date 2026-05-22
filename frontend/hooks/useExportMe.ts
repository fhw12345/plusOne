"use client";

import { useMutation } from "@tanstack/react-query";

import { exportMe } from "@/lib/api/me";

/**
 * Trigger a JSON export download of the current user's data. Pure
 * side-effect — no cache to update, no UI state beyond the mutation's
 * own ``isPending`` / ``error``.
 */
export function useExportMe() {
  return useMutation<void, unknown, void>({
    mutationFn: () => exportMe(),
  });
}
