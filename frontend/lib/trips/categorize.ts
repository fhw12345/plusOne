import type { JoinedItem, JoinedItemView } from "@/lib/schemas/trips";
import { isDisagreement } from "@/lib/trips/disagreement";

export type TabKey =
  | "together"
  | "user_only"
  | "partner_only"
  | "disagreement"
  | "local_gems"
  | "tourist_traps";

export const TAB_ORDER: TabKey[] = [
  "together",
  "user_only",
  "partner_only",
  "disagreement",
  "local_gems",
  "tourist_traps",
];

export const TAB_LABELS: Record<TabKey, string> = {
  together: "together",
  user_only: "you only",
  partner_only: "them only",
  disagreement: "two minds",
  local_gems: "local gems",
  tourist_traps: "tourist traps",
};

// Per-tab empty-state copy. Reads as "by design", not "broken".
export const TAB_EMPTY_COPY: Record<TabKey, string> = {
  together: "nothing here yet.",
  user_only:
    "no you-only picks yet — this opens up once per-person tastes are wired in.",
  partner_only:
    "no partner-only picks yet — coming once per-person tastes are wired in.",
  disagreement: "no disagreements for this one.",
  local_gems: "no local gems in this reading.",
  tourist_traps: "nothing flagged as a tourist trap here.",
};

// Categorize items into the six tab buckets.
//
// `together` includes every item; `local_gems` / `tourist_traps` filter
// by the fused `classification`. `disagreement` (added in batch 2i) uses
// `isDisagreement(item)` — see ``lib/trips/disagreement.ts`` and PRD
// batch2i §4.3. `user_only` / `partner_only` are still empty in v1.
export function categorize(items: JoinedItem[]): Record<TabKey, JoinedItem[]> {
  const buckets: Record<TabKey, JoinedItem[]> = {
    together: [],
    user_only: [],
    partner_only: [],
    disagreement: [],
    local_gems: [],
    tourist_traps: [],
  };
  for (const item of items) {
    const view = item as JoinedItemView;
    buckets.together.push(item);
    if (view.classification === "local_gem") buckets.local_gems.push(item);
    if (view.classification === "tourist_trap") buckets.tourist_traps.push(item);
    if (isDisagreement(item)) buckets.disagreement.push(item);
  }
  return buckets;
}
