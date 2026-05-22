"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";

import { deleteMe } from "@/lib/api/me";
import { useAuthStore } from "@/store/auth";

/**
 * Hard-delete the current user. On success: clear the persisted auth
 * store (note: the store exposes ``.clear()``, not ``clearSession``),
 * wipe the react-query cache so no stale per-user data is rendered on
 * the way out, and redirect to the unauthed landing.
 *
 * 409 responses (admin self-delete attempts) propagate to the caller as
 * a thrown ApiError so the dialog can show a tailored message without
 * blowing away the session.
 */
export function useDeleteMe() {
  const qc = useQueryClient();
  const router = useRouter();
  return useMutation<void, unknown, void>({
    mutationFn: () => deleteMe(),
    onSuccess: () => {
      useAuthStore.getState().clear();
      qc.clear();
      router.replace("/");
    },
  });
}
