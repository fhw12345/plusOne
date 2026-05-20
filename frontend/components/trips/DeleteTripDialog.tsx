"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Trash2 } from "lucide-react";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { deleteTrip } from "@/lib/api/trips";
import { ApiError } from "@/lib/api/client";

export interface DeleteTripDialogProps {
  tripId: string;
  // Kept on the prop list for future use (e.g. hiding the trigger when
  // PRD adds a "running" visual treatment); not used for client-side
  // gating today — the backend returns 409 which we surface inline.
  status: string;
}

export function DeleteTripDialog({ tripId, status: _status }: DeleteTripDialogProps) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleDelete = async () => {
    setPending(true);
    setError(null);
    try {
      await deleteTrip(tripId);
      setOpen(false);
      router.replace("/app");
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setError(
          "Cannot delete a trip while it's running. Wait for it to finish or be aborted, then try again.",
        );
      } else {
        setError("Could not delete this trip. Try again in a moment.");
      }
    } finally {
      setPending(false);
    }
  };

  return (
    <AlertDialog open={open} onOpenChange={setOpen}>
      <AlertDialogTrigger asChild>
        <Button variant="outline" size="sm" data-testid="delete-trip-button">
          <Trash2 className="h-4 w-4" />
          Delete
        </Button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Delete this trip?</AlertDialogTitle>
          <AlertDialogDescription>
            This permanently removes the trip and its report. This action cannot be undone.
          </AlertDialogDescription>
        </AlertDialogHeader>
        {error ? (
          <p role="alert" className="text-sm text-red-600">
            {error}
          </p>
        ) : null}
        <AlertDialogFooter>
          <AlertDialogCancel disabled={pending}>Cancel</AlertDialogCancel>
          <AlertDialogAction
            data-testid="delete-trip-confirm"
            onClick={(e) => {
              // Prevent the default Radix auto-close so we can show errors
              // (and keep the dialog open on 409).
              e.preventDefault();
              void handleDelete();
            }}
            disabled={pending}
            className="bg-red-600 text-white hover:bg-red-700"
          >
            {pending ? "Deleting…" : "Delete"}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
