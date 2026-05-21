"use client";

import { useState } from "react";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { createShare, revokeShare } from "@/lib/api/trips";

export interface ShareDialogProps {
  tripId: string;
}

interface ActiveShare {
  token: string;
  share_url: string;
  expires_at: string;
}

export function ShareDialog({ tripId }: ShareDialogProps) {
  const [open, setOpen] = useState(false);
  const [share, setShare] = useState<ActiveShare | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const handleMint = async () => {
    setPending(true);
    setError(null);
    try {
      const res = await createShare(tripId);
      setShare(res);
    } catch {
      setError("the link wouldn't mint. one more try?");
    } finally {
      setPending(false);
    }
  };

  const handleRevoke = async () => {
    if (!share) return;
    setPending(true);
    setError(null);
    try {
      await revokeShare(tripId, share.token);
      setShare(null);
    } catch {
      setError("couldn't pull the link back. try again?");
    } finally {
      setPending(false);
    }
  };

  const handleCopy = async () => {
    if (!share) return;
    if (typeof navigator !== "undefined" && navigator.clipboard) {
      await navigator.clipboard.writeText(share.share_url);
      setCopied(true);
      setTimeout(() => setCopied(false), 2_000);
    }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) {
          setShare(null);
          setError(null);
          setCopied(false);
        }
      }}
    >
      <DialogTrigger asChild>
        <button type="button" className="btn" data-testid="share-button">
          pass it along
        </button>
      </DialogTrigger>
      <DialogContent
        data-testid="share-dialog"
        style={{
          background: "hsl(var(--paper-2))",
          border: "1px solid hsl(var(--kraft))",
          boxShadow: "0 20px 36px -18px hsl(0 0% 0% / .35)",
          color: "hsl(var(--ink))",
        }}
      >
        <DialogHeader>
          <DialogTitle asChild>
            <p className="hand-lg" style={{ fontSize: 32 }}>
              pass this reading along
            </p>
          </DialogTitle>
          <DialogDescription asChild>
            <p className="scrawl" style={{ fontSize: 15 }}>
              anyone with the link can read it &mdash; nothing else. it stops working after 30
              days, or whenever you pull it back.
            </p>
          </DialogDescription>
        </DialogHeader>

        {error ? (
          <p role="alert" className="annot" style={{ display: "block" }}>
            {error}
          </p>
        ) : null}

        {share ? (
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <label
              htmlFor="share-url"
              className="type"
              style={{ color: "hsl(var(--ink-2))" }}
            >
              link
            </label>
            <div style={{ display: "flex", gap: 10 }}>
              <input
                id="share-url"
                readOnly
                value={share.share_url}
                data-testid="share-url"
                style={{
                  flex: 1,
                  padding: "8px 10px",
                  background: "hsl(var(--paper))",
                  border: "1px solid hsl(var(--kraft))",
                  font: "inherit",
                  color: "hsl(var(--ink))",
                  fontSize: 14,
                }}
              />
              <button
                type="button"
                onClick={handleCopy}
                data-testid="share-copy"
                className="btn"
              >
                {copied ? "copied!" : "copy"}
              </button>
            </div>
            <p className="scrawl" style={{ fontSize: 14, color: "hsl(var(--ink-3))" }}>
              expires {new Date(share.expires_at).toLocaleString()}
            </p>
          </div>
        ) : (
          <p className="hand" style={{ fontSize: 20 }}>
            mint a one-off link to share this reading with someone.
          </p>
        )}

        <DialogFooter>
          {share ? (
            <button
              type="button"
              onClick={handleRevoke}
              disabled={pending}
              data-testid="share-revoke"
              className="btn"
              style={{ color: "hsl(var(--signal-snag))" }}
            >
              {pending ? "pulling…" : "pull it back"}
            </button>
          ) : (
            <button
              type="button"
              onClick={handleMint}
              disabled={pending}
              data-testid="share-create"
              className="btn btn--red"
            >
              {pending ? "minting…" : "mint a link"}
            </button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
