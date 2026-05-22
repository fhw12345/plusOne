import type { JoinedItem, JoinedItemView } from "@/lib/schemas/trips";
import { isDisagreement } from "@/lib/trips/disagreement";
import { resolveClassification } from "@/lib/trips/resolveClassification";
import type { Perspective } from "@/store/reportPrefs";

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

// Per-tab empty-state copy. Reads as "by design", not "broken". Batch-2p
// retired the "coming once per-person tastes are wired in" sentinel on
// the score-gated tabs — the feature ships in this batch; an empty tab
// now means "this particular reading didn't surface any picks here".
export const TAB_EMPTY_COPY: Record<TabKey, string> = {
  together: "nothing here yet.",
  user_only: "no you-only picks in this reading.",
  partner_only: "no them-only picks in this reading.",
  disagreement: "no disagreements for this one.",
  local_gems: "no local gems in this reading.",
  tourist_traps: "nothing flagged as a tourist trap here.",
};

// Score thresholds for the score-gated tabs (PRD batch-2p §4.2). Strict
// ``>`` / ``<`` at the boundary (a 0.6 exactly does NOT route to
// ``user_only``).
const USER_HIGH = 0.6;
const USER_LOW = 0.4;
const COMPANION_HIGH = 0.6;
const COMPANION_LOW = 0.4;

export interface Party {
  user_id: string;
  companion_ids: string[];
}

function getMatchScores(view: JoinedItemView): Record<string, number> | null {
  return view.match_scores ?? null;
}

function userScore(view: JoinedItemView, party: Party): number | null {
  const scores = getMatchScores(view);
  if (scores == null) return null;
  const v = scores[party.user_id];
  return typeof v === "number" ? v : null;
}

function companionScores(view: JoinedItemView, party: Party): number[] {
  const scores = getMatchScores(view);
  if (scores == null) return [];
  const out: number[] = [];
  for (const id of party.companion_ids) {
    const v = scores[id];
    if (typeof v === "number") out.push(v);
  }
  return out;
}

function isUserOnly(view: JoinedItemView, party: Party): boolean {
  // Solo-trip guard (PRD batch-2p §3 S2): with zero companions the
  // ``every companion_score < 0.4`` check is vacuously true, which would
  // shadow every item into ``user_only``. Skip the route entirely.
  if (party.companion_ids.length === 0) return false;
  const u = userScore(view, party);
  if (u == null) return false;
  const cs = companionScores(view, party);
  if (cs.length === 0) return false;
  return u > USER_HIGH && cs.every((c) => c < COMPANION_LOW);
}

function isPartnerOnly(view: JoinedItemView, party: Party): boolean {
  if (party.companion_ids.length === 0) return false;
  const u = userScore(view, party);
  if (u == null) return false;
  const cs = companionScores(view, party);
  if (cs.length === 0) return false;
  return cs.every((c) => c > COMPANION_HIGH) && u < USER_LOW;
}

// Categorize items into the six tab buckets.
//
// `together` includes every item; `local_gems` / `tourist_traps` filter
// by the per-perspective classification (PRD batch-2r §4.2) via
// `resolveClassification(item, perspective)`, which falls back to the
// fused `classification` when the per-side field is null/missing.
// `disagreement` (batch 2i) uses `isDisagreement(item)` which reads the
// raw `classification_en` / `classification_zh` pair directly — it is
// the META view of zh-vs-en divergence and stays perspective-agnostic
// by construction.
//
// Batch-2p: `user_only` / `partner_only` use per-item `match_scores`
// keyed against the trip's ``party``. When ``party`` is missing (old
// reports / shared endpoint pre-2p) the score-gated tabs stay empty.
export function categorize(
  items: JoinedItem[],
  perspective: Perspective = "fused",
  party?: Party | null,
): Record<TabKey, JoinedItem[]> {
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
    const cls = resolveClassification(item, perspective);
    buckets.together.push(item);
    if (cls === "local_gem") buckets.local_gems.push(item);
    if (cls === "tourist_trap") buckets.tourist_traps.push(item);
    if (isDisagreement(item)) buckets.disagreement.push(item);
    if (party) {
      if (isUserOnly(view, party)) buckets.user_only.push(item);
      if (isPartnerOnly(view, party)) buckets.partner_only.push(item);
    }
  }
  return buckets;
}
