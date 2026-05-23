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
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { useDeleteMe } from "@/hooks/useDeleteMe";
import { ApiError } from "@/lib/api/client";

const CONFIRM_WORD = "DELETE";

const ADMIN_BLOCKED_COPY =
  "admins can't tear out their own page. ask another admin, or remove the admin flag first.";
const GENERIC_ERROR_COPY = "couldn't tear it out. one more try?";

export interface DeleteAccountDialogProps {
  /**
   * Override the destructive mutation for tests so the dialog can be
   * exercised without spinning up a QueryClient + router. Production code
   * leaves this unset and lets the default ``useDeleteMe()`` hook drive.
   */
  mutate?: () => Promise<void>;
}

export function DeleteAccountDialog({ mutate }: DeleteAccountDialogProps = {}) {
  const del = useDeleteMe();
  const [open, setOpen] = React.useState(false);
  const [confirm, setConfirm] = React.useState("");
  const [pending, setPending] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const run = mutate ?? (() => del.mutateAsync());

  const handleOpenChange = (next: boolean) => {
    setOpen(next);
    if (!next) {
      setConfirm("");
      setError(null);
    }
  };

  const handleConfirm = async () => {
    setPending(true);
    setError(null);
    try {
      await run();
      // On success the hook clears auth + navigates; close defensively.
      setOpen(false);
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setError(ADMIN_BLOCKED_COPY);
      } else {
        setError(GENERIC_ERROR_COPY);
      }
    } finally {
      setPending(false);
    }
  };

  const canConfirm = confirm === CONFIRM_WORD && !pending;

  return (
    <AlertDialog open={open} onOpenChange={handleOpenChange}>
      <AlertDialogTrigger asChild>
        <button type="button" className="btn btn--red" data-testid="delete-account-button">
          tear it all out
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
              tear it all out?
            </p>
          </AlertDialogTitle>
          <AlertDialogDescription asChild>
            <p className="scrawl" style={{ fontSize: 15 }}>
              this clears everything. no putting it back. last chance.
            </p>
          </AlertDialogDescription>
        </AlertDialogHeader>
        <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 12 }}>
          <label htmlFor="delete-account-confirm-input" className="annot" style={{ fontSize: 14 }}>
            type DELETE to confirm
          </label>
          <input
            id="delete-account-confirm-input"
            type="text"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            aria-label="type DELETE to confirm"
            autoComplete="off"
            spellCheck={false}
            disabled={pending}
            style={{
              font: "inherit",
              fontSize: 18,
              padding: "6px 10px",
              border: "1px solid hsl(var(--kraft))",
              background: "hsl(var(--paper-1))",
              color: "hsl(var(--ink))",
            }}
          />
        </div>
        {error ? (
          <p role="alert" className="annot" style={{ display: "block", marginTop: 10 }}>
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
              if (!canConfirm) return;
              void handleConfirm();
            }}
          >
            <button
              type="button"
              data-testid="delete-account-confirm"
              disabled={!canConfirm}
              className="btn btn--red"
              style={{ opacity: !canConfirm ? 0.55 : 1 }}
            >
              {pending ? "tearing…" : "yes, tear it out"}
            </button>
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
