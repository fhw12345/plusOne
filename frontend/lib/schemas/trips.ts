import { z } from "zod";

// Batch-2o: closed currency whitelist (mirrors backend
// ``_ALLOWED_CURRENCIES`` in api/trips.py). Extending is a deliberate
// product call — keep it narrow.
export const CURRENCIES = ["USD", "EUR", "JPY", "CNY", "GBP", "TWD", "KRW", "AUD"] as const;
export const Currency = z.enum(CURRENCIES);
export type Currency = z.infer<typeof Currency>;

// Mirror of backend `CreateTripBody`
// (backend/src/plus_one/api/trips.py:34-43). `companion_ids` is optional
// on the wire (backend defaults to `[]`); when non-empty, the runner
// filters AgentContext.selected_companions to that subset.
//
// Batch-2o adds four optional structured hints: date_start, date_end,
// budget_amount, budget_currency. All four are independently optional;
// the cross-field check (end>=start) lives in the ``superRefine`` below.
export const CreateTripBody = z
  .object({
    destination: z.string().min(1, "destination is required").max(200),
    free_text: z.string().max(2000).optional(),
    companion_ids: z.array(z.string().uuid()).max(50).optional(),
    date_start: z.string().datetime({ offset: true }).optional(),
    date_end: z.string().datetime({ offset: true }).optional(),
    budget_amount: z
      .number()
      .int("whole numbers only.")
      .nonnegative("budget can't be negative.")
      .max(10_000_000)
      .optional(),
    budget_currency: Currency.optional(),
  })
  .superRefine((val, ctx) => {
    if (val.date_start && val.date_end && val.date_end < val.date_start) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["date_end"],
        message: "the end is before the start. flip them?",
      });
    }
  });
export type CreateTripBody = z.infer<typeof CreateTripBody>;

export const CreateTripResponse = z.object({
  trip_id: z.string().uuid(),
  status: z.string(),
  // batch-2t: 0–3 clarifier questions surfaced when ``status === "clarifying"``.
  // Backend always returns an array (empty list on the pass-through path);
  // we accept missing for backward compatibility with pre-2t fixtures.
  clarifier_questions: z
    .array(
      z.object({
        id: z.string().min(1),
        text: z.string().min(1),
      }),
    )
    .optional()
    .default([]),
});
export type CreateTripResponse = z.infer<typeof CreateTripResponse>;

// batch-2t: client-side answer shape sent to POST /api/trips/{id}/clarify.
export const ClarifierAnswer = z.object({
  id: z.string().min(1),
  text: z.string().min(1, "give me something here or skip.").max(1000),
});
export type ClarifierAnswer = z.infer<typeof ClarifierAnswer>;

export const ClarifyBody = z.object({
  answers: z.array(ClarifierAnswer).min(1).max(3),
});
export type ClarifyBody = z.infer<typeof ClarifyBody>;

export const ClarifyResponse = z.object({
  status: z.string(),
});
export type ClarifyResponse = z.infer<typeof ClarifyResponse>;

export const TripStatus = z.enum(["pending", "clarifying", "running", "complete", "aborted"]);
export type TripStatus = z.infer<typeof TripStatus>;

// JoinedItem shape is intentionally loose for v1 — the backend's
// `JoinedItem.model_dump(mode="json")` payload is not yet frozen
// (see backend/src/plus_one/services/trip_runner.py:144).
export const JoinedItemSchema = z.object({}).passthrough();
export type JoinedItem = z.infer<typeof JoinedItemSchema>;

// PRD batch-3a — itinerary day plan. Backend stores ``day_plan`` as a
// JSONB array under ``TripContent``; each ``DaySlot.item_index`` is a
// 0-based pointer into ``content.items``. Periods are a closed set
// (mirrors backend ``Literal["morning", ...]``).
export const DaySlot = z.object({
  period: z.enum(["morning", "afternoon", "evening", "late_night"]),
  item_index: z.number().int().nonnegative(),
  note: z.string().nullable().optional(),
});
export type DaySlot = z.infer<typeof DaySlot>;

export const DayPlan = z.object({
  day_index: z.number().int().positive(),
  date: z.string().nullable().optional(),
  theme: z.string().nullable().optional(),
  slots: z.array(DaySlot),
});
export type DayPlan = z.infer<typeof DayPlan>;

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
    source?: "reddit" | "xiaohongshu" | "foursquare";
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
  // Batch-2p — per-person match scores keyed by user.id / companion.id.
  // Float 0..1. Null on solo trips or pre-2p items.
  match_scores?: Record<string, number> | null;
  // PRD batch-3a — Foursquare cover image (deterministic, no LLM) and
  // joiner-v4 long-form description (2–4 sentences). Both optional:
  // pre-3a items lack them and rendering surfaces fall back gracefully.
  image_url?: string | null;
  long_description?: string;
};

// Per-language sub-shape for `translations[lang]`. Batch-2q widens it
// from a bare array of items to an object carrying both `items` and an
// optional `tl_dr`. We accept either shape on the wire and normalise to
// the object form so call sites can always read `translations[lang].items`.
// Reports written between batch-2k and batch-2q have the bare-array
// payload; reports written from batch-2q forward have the object.
const TripContentTranslation = z
  .union([
    z.array(JoinedItemSchema),
    z.object({
      items: z.array(JoinedItemSchema).optional(),
      tl_dr: z.string().nullable().optional(),
    }),
  ])
  .transform((v) => (Array.isArray(v) ? { items: v } : v));

export const TripContent = z.object({
  items: z.array(JoinedItemSchema),
  // Batch-2q — report-level TL;DR paragraph. Pre-2q reports omit.
  tl_dr: z.string().nullable().optional(),
  // PRD batch 2k §6.3 Option B: translations live alongside the source
  // items under a per-language key. Optional + per-lang optional so old
  // reports (pre-batch-2k) still validate and the frontend's fallback
  // path (`translations[lang] ?? items`) handles them.
  translations: z
    .object({
      en: TripContentTranslation.optional(),
      zh: TripContentTranslation.optional(),
    })
    .partial()
    .optional(),
  // PRD batch-3a — day-by-day itinerary, optional and nullable so old
  // reports (no scheduler run) and trips where the scheduler failed
  // validation fall back to ``<ReportView>``.
  day_plan: z.array(DayPlan).nullable().optional(),
});
export type TripContent = z.infer<typeof TripContent>;

// Batch-2p: identity of who's on the trip. Carried on TripDetail so the
// frontend can render labels like `match  you: 0.8 · alice: 0.3` for
// the per-person scores on each card.
export const TripParty = z.object({
  user_id: z.string().uuid(),
  companion_ids: z.array(z.string().uuid()),
});
export type TripParty = z.infer<typeof TripParty>;

export const TripDetail = z.object({
  trip_id: z.string().uuid(),
  destination: z.string(),
  status: TripStatus,
  latest_report_id: z.string().uuid().nullable(),
  content: TripContent.nullable(),
  // Batch-2o: mirror the four optional structured hints. Pre-2o trips
  // return ``null`` for each; new trips echo what the user submitted.
  date_start: z.string().datetime({ offset: true }).nullable().optional(),
  date_end: z.string().datetime({ offset: true }).nullable().optional(),
  budget_amount: z.number().int().nonnegative().nullable().optional(),
  budget_currency: Currency.nullable().optional(),
  // Batch-2p: optional party block so the frontend can resolve
  // ``match_scores`` keys to display names.
  party: TripParty.nullable().optional(),
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

// === Share ================================================================

// Mirror of backend `CreateShareResponse` (backend/src/plus_one/api/trips.py).
export const CreateShareResponse = z.object({
  token: z.string().min(1),
  share_url: z.string().url(),
  expires_at: z.string().datetime({ offset: true }),
});
export type CreateShareResponse = z.infer<typeof CreateShareResponse>;

// Mirror of backend `SharedTripResponse`
// (backend/src/plus_one/api/shared.py). Note the deliberate absence of
// `user_id`, `created_by`, `trace`, `input_tokens`, `output_tokens` —
// the public endpoint strips them.
export const SharedTripResponse = z.object({
  trip_id: z.string().uuid(),
  destination: z.string(),
  status: TripStatus,
  content: TripContent.nullable(),
  shared: z.literal(true),
  expires_at: z.string().datetime({ offset: true }),
});
export type SharedTripResponse = z.infer<typeof SharedTripResponse>;

// === Refine (batch-2u) ====================================================

// Mirror of backend `RefineTripBody` — single hint string, 1-500 chars.
// We don't bother trimming here; the backend strips whitespace and the
// UI's send-button disables when the field is empty after .trim().
export const RefineTripBody = z.object({
  hint: z.string().min(1).max(500),
});
export type RefineTripBody = z.infer<typeof RefineTripBody>;

export const RefineTripResponse = z.object({
  report_id: z.string().uuid(),
  status: z.string(),
});
export type RefineTripResponse = z.infer<typeof RefineTripResponse>;

// One entry in the trip's revision list. `is_original` differentiates the
// initial cycle's report from a refine; `hint` + `previous_report_id` are
// non-null only on refine rows.
export const TripReportSummary = z.object({
  report_id: z.string().uuid(),
  created_at: z.string().datetime({ offset: true }),
  is_original: z.boolean(),
  hint: z.string().nullable(),
  previous_report_id: z.string().uuid().nullable(),
});
export type TripReportSummary = z.infer<typeof TripReportSummary>;

export const TripReportsResponse = z.object({
  reports: z.array(TripReportSummary),
});
export type TripReportsResponse = z.infer<typeof TripReportsResponse>;
