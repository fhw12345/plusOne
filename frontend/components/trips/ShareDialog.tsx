"use client";

import { useState } from "react";
import { Copy, Share2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
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
      setError("Could not create the share link. Try again.");
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
      setError("Could not revoke the share link. Try again.");
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
          // Reset transient state on close so reopening starts clean.
          setShare(null);
          setError(null);
          setCopied(false);
        }
      }}
    >
      <DialogTrigger asChild>
        <Button variant="outline" size="sm" data-testid="share-button">
          <Share2 className="h-4 w-4" />
          Share
        </Button>
      </DialogTrigger>
      <DialogContent data-testid="share-dialog">
        <DialogHeader>
          <DialogTitle>Share this trip</DialogTitle>
          <DialogDescription>
            Anyone with the link can view the report read-only. Links expire after 30 days; revoke
            any time.
          </DialogDescription>
        </DialogHeader>

        {error ? (
          <p role="alert" className="text-sm text-red-600">
            {error}
          </p>
        ) : null}

        {share ? (
          <div className="flex flex-col gap-3">
            <label className="text-foreground/80 text-xs font-medium" htmlFor="share-url">
              Share URL
            </label>
            <div className="flex gap-2">
              <Input id="share-url" readOnly value={share.share_url} data-testid="share-url" />
              <Button
                type="button"
                variant="secondary"
                size="sm"
                onClick={handleCopy}
                data-testid="share-copy"
              >
                <Copy className="h-4 w-4" />
                {copied ? "Copied" : "Copy"}
              </Button>
            </div>
            <p className="text-muted-foreground text-xs">
              Expires {new Date(share.expires_at).toLocaleString()}
            </p>
          </div>
        ) : (
          <p className="text-muted-foreground text-sm">
            Generate a public link to share this trip with someone.
          </p>
        )}

        <DialogFooter>
          {share ? (
            <Button
              type="button"
              variant="destructive"
              onClick={handleRevoke}
              disabled={pending}
              data-testid="share-revoke"
            >
              {pending ? "Revoking…" : "Revoke link"}
            </Button>
          ) : (
            <Button
              type="button"
              onClick={handleMint}
              disabled={pending}
              data-testid="share-create"
            >
              {pending ? "Creating…" : "Create share link"}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
