"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

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
import { deleteTrip } from "@/lib/api/trips";
import { ApiError } from "@/lib/api/client";

export interface DeleteTripDialogProps {
  tripId: string;
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
        setError("can't tear out a page that's still being written. wait for it to finish first.");
      } else {
        setError("couldn't tear this out. one more try?");
      }
    } finally {
      setPending(false);
    }
  };

  return (
    <AlertDialog open={open} onOpenChange={setOpen}>
      <AlertDialogTrigger asChild>
        <button type="button" className="btn" data-testid="delete-trip-button">
          tear it out
        </button>
      </AlertDialogTrigger>
      <AlertDialogContent
        style={{
          background: "hsl(var(--paper-2))",
          border: "1px solid hsl(var(--kraft))",
          boxShadow: "0 20px 36px -18px hsl(0 0% 0% / .35)",
          color: "hsl(var(--ink))",
        }}
      >
        <AlertDialogHeader>
          <AlertDialogTitle asChild>
            <p className="hand-lg" style={{ fontSize: 30 }}>
              tear this page out?
            </p>
          </AlertDialogTitle>
          <AlertDialogDescription asChild>
            <p className="scrawl" style={{ fontSize: 15 }}>
              the reading goes with it &mdash; for good. no putting it back.
            </p>
          </AlertDialogDescription>
        </AlertDialogHeader>
        {error ? (
          <p role="alert" className="annot" style={{ display: "block" }}>
            {error}
          </p>
        ) : null}
        <AlertDialogFooter>
          <AlertDialogCancel asChild>
            <button
              type="button"
              className="link-hand"
              disabled={pending}
              style={{ font: "inherit", fontSize: 18, background: "none", border: 0, padding: 0 }}
            >
              never mind
            </button>
          </AlertDialogCancel>
          <AlertDialogAction
            asChild
            onClick={(e) => {
              e.preventDefault();
              void handleDelete();
            }}
          >
            <button
              type="button"
              data-testid="delete-trip-confirm"
              disabled={pending}
              className="btn btn--red"
              style={{ opacity: pending ? 0.55 : 1 }}
            >
              {pending ? "tearing…" : "yes, tear it out"}
            </button>
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
