import type { JoinedItem, JoinedItemView } from "@/lib/schemas/trips";

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
  together: "🤝 Together",
  user_only: "🚶 You-only",
  partner_only: "🚶‍♀️ Partner-only",
  disagreement: "⚠️ Disagreement",
  local_gems: "🌟 Local Gems",
  tourist_traps: "⚠️ Tourist Traps",
};

// Per-tab empty-state copy. Reads as "by design", not "broken".
export const TAB_EMPTY_COPY: Record<TabKey, string> = {
  together: "No items in this trip yet.",
  user_only:
    "No you-only items yet. Coming in a future update once per-person preferences are wired in.",
  partner_only:
    "No partner-only items yet. Coming in a future update once per-person preferences are wired in.",
  disagreement: "No disagreements flagged. Disagreement detection is coming in a future update.",
  local_gems: "No local gems in this report.",
  tourist_traps: "No tourist traps flagged in this report.",
};

// Categorize items into the six tab buckets.
//
// Today the backend persists `classification` (local_gem / tourist_trap /
// neutral / insufficient) but NOT `who_for` / disagreement signals — see
// PRD batch2g-pr-a §3.2. So `together` includes every item, `local_gems` /
// `tourist_traps` filter by classification, and the remaining tabs are
// always empty in v1.
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
  }
  return buckets;
}
