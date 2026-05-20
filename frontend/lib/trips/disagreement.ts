import type { JoinedItem, JoinedItemView } from "@/lib/schemas/trips";

/**
 * Mirror of backend ``DISAGREEMENT_THRESHOLD`` at
 * ``backend/src/plus_one/agents/_divergence.py``. Kept here as a constant
 * (not fetched from the API) because the backend never re-emits it and
 * the value rarely changes. If the backend constant moves, update both
 * places in the same PR.
 */
export const DISAGREEMENT_THRESHOLD = 0.5;

/**
 * Disagreement gate (matches PRD batch2i §4.3):
 * - both per-language classifications must be present (non-null), AND
 * - they must differ, AND
 * - the divergence score must be at or above the threshold.
 *
 * Missing fields (e.g. old reports produced before batch 2i) fall
 * through closed → ``false`` — no false-positive disagreements.
 */
export function isDisagreement(item: JoinedItem): boolean {
  const view = item as JoinedItemView;
  const en = view.classification_en ?? null;
  const zh = view.classification_zh ?? null;
  if (en == null || zh == null) return false;
  if (en === zh) return false;
  return (view.divergence_score ?? 0) >= DISAGREEMENT_THRESHOLD;
}
