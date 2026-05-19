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
