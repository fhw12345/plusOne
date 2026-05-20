"use client";

import { useId, useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import type { JoinedItem, JoinedItemView } from "@/lib/schemas/trips";
import { cn } from "@/lib/utils";

export interface ItemCardProps {
  item: JoinedItem;
}

function classificationBadge(classification: JoinedItemView["classification"]) {
  switch (classification) {
    case "local_gem":
      return { label: "Local gem", variant: "success" as const };
    case "tourist_trap":
      return { label: "Tourist trap", variant: "danger" as const };
    case "neutral":
      return { label: "Neutral", variant: "muted" as const };
    case "insufficient":
      return { label: "Low evidence", variant: "outline" as const };
    default:
      return null;
  }
}

function shortHost(url: string | undefined): string {
  if (!url) return "";
  try {
    return new URL(url).host.replace(/^www\./, "");
  } catch {
    return url.slice(0, 40);
  }
}

function truncate(s: string, n = 140): string {
  if (s.length <= n) return s;
  return s.slice(0, n - 1).trimEnd() + "…";
}

export function ItemCard({ item }: ItemCardProps) {
  const view = item as JoinedItemView;
  const name = view.candidate?.name ?? "Untitled";
  const evidence = view.evidence ?? [];
  const evidenceCount = evidence.length;
  const badge = classificationBadge(view.classification);
  const confidence =
    typeof view.confidence === "number" && !Number.isNaN(view.confidence)
      ? Math.round(view.confidence * 100)
      : null;
  const area = view.candidate?.area ?? null;
  const style = view.candidate?.style ?? null;
  const summary = view.summary ?? "";
  const rationale = view.candidate?.rationale ?? "";

  const [open, setOpen] = useState(false);
  const bodyId = useId();

  const areaStyleLine = [area, style].filter(Boolean).join(" · ");

  return (
    <Card>
      <CardHeader className="gap-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex min-w-0 flex-1 items-center gap-2">
            <span className="text-foreground truncate text-base font-medium">{name}</span>
            {badge ? <Badge variant={badge.variant}>{badge.label}</Badge> : null}
            {evidenceCount > 0 ? <Badge variant="outline">{evidenceCount} sources</Badge> : null}
          </div>
          <div className="flex items-center gap-2">
            {confidence !== null ? (
              <span className="text-foreground/70 text-xs">~{confidence}%</span>
            ) : null}
            <button
              type="button"
              onClick={() => setOpen((v) => !v)}
              aria-expanded={open}
              aria-controls={bodyId}
              aria-label={`${open ? "Hide" : "Show"} details for ${name}`}
              className="border-foreground/20 hover:bg-muted focus-visible:ring-foreground/60 inline-flex items-center justify-center rounded-md border p-1 transition-colors focus-visible:ring-2 focus-visible:outline-none"
            >
              {open ? (
                <ChevronDown aria-hidden="true" className="h-4 w-4" />
              ) : (
                <ChevronRight aria-hidden="true" className="h-4 w-4" />
              )}
            </button>
          </div>
        </div>
      </CardHeader>
      <CardContent id={bodyId} className={cn(open ? "block" : "hidden", "text-sm")}>
        <div className="flex flex-col gap-3">
          {areaStyleLine ? <p className="text-foreground/80">{areaStyleLine}</p> : null}
          {summary ? <p className="text-foreground/80">{summary}</p> : null}
          {evidence.length > 0 ? (
            <div className="flex flex-col gap-2">
              <p className="text-foreground/70 text-xs font-medium tracking-wide uppercase">
                Sources
              </p>
              <ul className="flex flex-col gap-2">
                {evidence.map((ev, idx) => {
                  const url = ev?.url ?? "";
                  const snippet = ev?.snippet ?? "";
                  const source = ev?.source ?? "source";
                  const label = `${source} · ${shortHost(url)}`;
                  return (
                    <li key={idx} className="flex flex-col gap-1">
                      {url ? (
                        <a
                          href={url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-foreground hover:text-foreground/80 truncate text-xs underline underline-offset-2"
                        >
                          {label}
                        </a>
                      ) : (
                        <span className="text-foreground/80 truncate text-xs">{label}</span>
                      )}
                      {snippet ? (
                        <span className="text-foreground/70 text-xs">{truncate(snippet)}</span>
                      ) : null}
                    </li>
                  );
                })}
              </ul>
            </div>
          ) : null}
          {rationale ? (
            <p className="text-foreground/70 text-xs">
              <span className="font-medium">Why this came up:</span> {rationale}
            </p>
          ) : null}
        </div>
      </CardContent>
    </Card>
  );
}
