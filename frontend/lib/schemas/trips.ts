import { z } from "zod";

// Mirror of backend `CreateTripBody`
// (backend/src/plus_one/api/trips.py:34-36).
export const CreateTripBody = z.object({
  destination: z.string().min(1, "Destination is required").max(200),
  free_text: z.string().max(2000).optional(),
});
export type CreateTripBody = z.infer<typeof CreateTripBody>;

export const CreateTripResponse = z.object({
  trip_id: z.string().uuid(),
  status: z.string(),
});
export type CreateTripResponse = z.infer<typeof CreateTripResponse>;

export const TripStatus = z.enum(["pending", "running", "complete", "aborted"]);
export type TripStatus = z.infer<typeof TripStatus>;

// JoinedItem shape is intentionally loose for v1 — the backend's
// `JoinedItem.model_dump(mode="json")` payload is not yet frozen
// (see backend/src/plus_one/services/trip_runner.py:144).
export const JoinedItemSchema = z.object({}).passthrough();
export type JoinedItem = z.infer<typeof JoinedItemSchema>;

// View-only structural type matching the actual JoinedItem fields the
// backend joiner emits today. Used by ReportView / ItemCard / categorize
// to pull out known fields (candidate, classification, evidence, etc.)
// without enforcing them at the zod boundary — that stays passthrough
// so unknown future fields don't get stripped. Cast at the use site.
export type JoinedItemView = {
  candidate?: {
    name?: string;
    area?: string | null;
    style?: string | null;
    rationale?: string;
  };
  classification?: "local_gem" | "tourist_trap" | "neutral" | "insufficient";
  confidence?: number;
  evidence?: Array<{
    source?: "reddit" | "xiaohongshu" | "google_places";
    url?: string;
    snippet?: string;
    sentiment?: number | null;
  }>;
  summary?: string;
  // Batch 2i — per-language sub-classifications and divergence score.
  // All three are optional: old reports (pre-2i) lack them and the
  // disagreement gate fails closed.
  classification_en?: "local_gem" | "tourist_trap" | "neutral" | "insufficient" | null;
  classification_zh?: "local_gem" | "tourist_trap" | "neutral" | "insufficient" | null;
  divergence_score?: number;
};

export const TripContent = z.object({
  items: z.array(JoinedItemSchema),
});
export type TripContent = z.infer<typeof TripContent>;

export const TripDetail = z.object({
  trip_id: z.string().uuid(),
  destination: z.string(),
  status: TripStatus,
  latest_report_id: z.string().uuid().nullable(),
  content: TripContent.nullable(),
});
export type TripDetail = z.infer<typeof TripDetail>;

// Mirror of backend `TripListItem` (backend/src/plus_one/api/trips.py).
export const TripListItem = z.object({
  trip_id: z.string().uuid(),
  destination: z.string(),
  status: TripStatus,
  created_at: z.string().datetime({ offset: true }),
  latest_report_id: z.string().uuid().nullable(),
  has_report: z.boolean(),
});
export type TripListItem = z.infer<typeof TripListItem>;

export const TripListResponse = z.object({
  trips: z.array(TripListItem),
  next_cursor: z.string().nullable(),
});
export type TripListResponse = z.infer<typeof TripListResponse>;
