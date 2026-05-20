"use client";

import * as React from "react";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { useDeleteCompanion } from "@/hooks/useCompanions";
import type { CompanionResponse } from "@/lib/schemas/companions";

interface DeleteCompanionDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  companion?: CompanionResponse;
}

/**
 * Destructive-confirmation pattern using AlertDialog (not Dialog) so screen
 * readers announce it with the correct ARIA role. See PRD §5 + §G2.
 */
export function DeleteCompanionDialog({
  open,
  onOpenChange,
  companion,
}: DeleteCompanionDialogProps) {
  const del = useDeleteCompanion();
  const [serverError, setServerError] = React.useState<string | null>(null);

  const handleOpenChange = (next: boolean) => {
    if (next) setServerError(null);
    onOpenChange(next);
  };

  const onConfirm = async () => {
    if (!companion) return;
    setServerError(null);
    try {
      await del.mutateAsync(companion.id);
      onOpenChange(false);
    } catch {
      setServerError("Couldn't delete companion. Please try again.");
    }
  };

  return (
    <AlertDialog open={open} onOpenChange={handleOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Delete companion?</AlertDialogTitle>
          <AlertDialogDescription>
            {companion ? `"${companion.name}" will be removed from your companions.` : ""} This
            can&apos;t be undone.
          </AlertDialogDescription>
        </AlertDialogHeader>
        {serverError ? (
          <p role="alert" className="text-sm text-red-600">
            {serverError}
          </p>
        ) : null}
        <AlertDialogFooter>
          <AlertDialogCancel disabled={del.isPending}>Cancel</AlertDialogCancel>
          <AlertDialogAction
            onClick={(e) => {
              // Prevent radix's default close-on-action; we only close on 2xx.
              e.preventDefault();
              void onConfirm();
            }}
            disabled={del.isPending}
          >
            {del.isPending ? "Deleting…" : "Delete"}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
