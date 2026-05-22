import type { JoinedItem, JoinedItemView } from "@/lib/schemas/trips";
import type { Perspective } from "@/store/reportPrefs";

/**
 * Per-perspective classification resolver (PRD batch-2r §4.2).
 *
 * Returns the per-side classification when the requested perspective is
 * ``zh`` or ``en`` and the per-side field is non-null; otherwise falls
 * back to the fused ``classification``. ``fused`` always returns the
 * fused field. Old (pre-2i) reports lack the per-side fields entirely
 * and therefore always resolve to the fused field under every
 * perspective — this is the graceful-fallback behaviour S3 in the PRD
 * relies on. Returns ``undefined`` only when the fused field is also
 * absent (item then has no verdict pill, matching today's behaviour).
 */
export function resolveClassification(
  item: JoinedItem,
  perspective: Perspective,
): JoinedItemView["classification"] | undefined {
  const view = item as JoinedItemView;
  if (perspective === "zh") return view.classification_zh ?? view.classification;
  if (perspective === "en") return view.classification_en ?? view.classification;
  return view.classification;
}
