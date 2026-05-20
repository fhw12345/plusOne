import type { JoinedItemView, TripDetail } from "@/lib/schemas/trips";

/**
 * Render a {@link TripDetail} as a Markdown document. Pure function — no
 * DOM access, so callable from server components if ever needed.
 *
 * Layout: title, status/date metadata, then sections for Local Gems,
 * Tourist Traps, Neutral, and Low evidence. Items missing a known
 * classification are bucketed into "Other".
 */
export function reportToMarkdown(trip: TripDetail): string {
  const lines: string[] = [];
  lines.push(`# Trip to ${escapeInline(trip.destination)}`);
  lines.push("");
  lines.push(`Status: **${trip.status}**`);
  lines.push("");
  lines.push("---");

  const items = (trip.content?.items ?? []) as JoinedItemView[];
  const buckets: Record<string, JoinedItemView[]> = {
    local_gem: [],
    tourist_trap: [],
    neutral: [],
    insufficient: [],
    other: [],
  };
  for (const it of items) {
    const key = it.classification ?? "other";
    const bucket = buckets[key] ?? buckets.other;
    bucket!.push(it);
  }

  const sections: Array<[string, string]> = [
    ["local_gem", "Local Gems"],
    ["tourist_trap", "Tourist Traps"],
    ["neutral", "Neutral"],
    ["insufficient", "Low evidence"],
    ["other", "Other"],
  ];

  for (const [key, label] of sections) {
    const bucket = buckets[key];
    if (!bucket || bucket.length === 0) continue;
    lines.push("");
    lines.push(`## ${label}`);
    lines.push("");
    for (const item of bucket) {
      const name = item.candidate?.name ?? "Untitled";
      const summary = item.summary ?? item.candidate?.rationale ?? "";
      lines.push(`- **${escapeInline(name)}**${summary ? `: ${escapeInline(summary)}` : ""}`);
      if (item.evidence && item.evidence.length > 0) {
        const links = item.evidence
          .filter((e) => !!e.url)
          .map((e) => `[${e.source ?? "source"}](${e.url})`)
          .join(", ");
        if (links.length > 0) {
          lines.push(`  - Sources: ${links}`);
        }
      }
    }
  }

  if (items.length === 0) {
    lines.push("");
    lines.push("_No results yet._");
  }

  lines.push("");
  return lines.join("\n");
}

/**
 * Trigger a client-side `.md` download for the given trip. Safe no-op when
 * `window` is undefined (server / test contexts).
 */
export function downloadMarkdown(trip: TripDetail): void {
  if (typeof window === "undefined") return;
  const md = reportToMarkdown(trip);
  const blob = new Blob([md], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);

  const today = new Date().toISOString().slice(0, 10);
  const filename = `${slugify(trip.destination)}-${today}.md`;

  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  // Revoke on next tick so the browser has finished initiating the
  // download before the URL is freed.
  setTimeout(() => URL.revokeObjectURL(url), 0);
}

/** Replace characters that break Markdown table/inline parsing. */
function escapeInline(value: string): string {
  // Pipe is the only character that breaks Markdown structure here (in
  // case our markdown ever lands inside a table). Backslashes are
  // preserved as-is since we never emit raw HTML.
  return value.replace(/\|/g, "\\|");
}

/** ASCII-safe filename slug; non-ASCII chars are dropped. */
function slugify(value: string): string {
  const slug = value
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return slug || "trip";
}
