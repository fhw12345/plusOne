import type { TripStatus } from "@/lib/schemas/trips";

const MS_PER_MINUTE = 60_000;
const MS_PER_HOUR = MS_PER_MINUTE * 60;
const MS_PER_DAY = MS_PER_HOUR * 24;

/**
 * Hybrid date formatter for trip cards:
 *   - <60s  → "just now"
 *   - <60m  → "N minutes ago" (Intl.RelativeTimeFormat)
 *   - <24h  → "N hours ago"
 *   - <7d   → "N days ago"
 *   - older → absolute YYYY-MM-DD
 *
 * No `date-fns` / `dayjs` dependency — `Intl.RelativeTimeFormat` is a
 * browser built-in available in every modern runtime Playwright touches.
 * PRD §8.1.
 */
export function formatTripDate(iso: string, now: number = Date.now()): string {
  const then = new Date(iso).getTime();
  const diffMs = now - then;
  if (diffMs < MS_PER_MINUTE) return "just now";

  const rtf = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
  if (diffMs < MS_PER_HOUR) {
    return rtf.format(-Math.floor(diffMs / MS_PER_MINUTE), "minute");
  }
  if (diffMs < MS_PER_DAY) {
    return rtf.format(-Math.floor(diffMs / MS_PER_HOUR), "hour");
  }
  if (diffMs < 7 * MS_PER_DAY) {
    return rtf.format(-Math.floor(diffMs / MS_PER_DAY), "day");
  }
  return new Date(iso).toISOString().slice(0, 10);
}

export interface StatusMeta {
  label: string;
  classes: string;
}

// Aborted = muted gray (NOT red). In the e2e harness every trip aborts by
// design, and a wall of red badges would be visually alarming and
// incorrect — abort is a terminal state, not an error. PRD §12.4.
export const TRIP_STATUS_META: Record<TripStatus, StatusMeta> = {
  pending: {
    label: "Pending",
    classes: "bg-foreground/10 text-foreground/70",
  },
  running: {
    label: "Running",
    classes: "bg-blue-100 text-blue-800",
  },
  complete: {
    label: "Complete",
    classes: "bg-green-100 text-green-800",
  },
  aborted: {
    label: "Aborted",
    classes: "bg-foreground/10 text-foreground/60",
  },
};
