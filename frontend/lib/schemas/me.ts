import { z } from "zod";

// Zod mirror of the backend export payload returned by GET /api/me/export
// (see backend/src/plus_one/api/me.py and PRD §5). Kept permissive on the
// inner blobs (Profile, Report content, Feedback text) because the export
// is faithful to whatever shape the DB holds — we don't want a schema bump
// in an unrelated module to brick the user's download.

export const ExportedUser = z
  .object({
    id: z.string(),
    email: z.string(),
    username: z.string(),
    is_admin: z.boolean(),
    is_active: z.boolean(),
    email_verified_at: z.string().nullable(),
    last_login_at: z.string().nullable(),
    created_at: z.string().nullable(),
    updated_at: z.string().nullable(),
  })
  .passthrough();
export type ExportedUser = z.infer<typeof ExportedUser>;

export const ExportedProfile = z
  .object({
    demographics: z.record(z.string(), z.unknown()),
    travel_style: z.record(z.string(), z.unknown()),
    explicit_preferences: z.record(z.string(), z.unknown()),
    visited_cities: z.array(z.unknown()),
  })
  .passthrough();
export type ExportedProfile = z.infer<typeof ExportedProfile>;

export const ExportedCompanion = z
  .object({
    id: z.string(),
    name: z.string(),
    explicit_preferences: z.record(z.string(), z.unknown()),
    constraints: z.record(z.string(), z.unknown()),
    created_at: z.string().nullable(),
    updated_at: z.string().nullable(),
  })
  .passthrough();
export type ExportedCompanion = z.infer<typeof ExportedCompanion>;

export const ExportedReport = z
  .object({
    id: z.string(),
    content: z.unknown(),
    input_tokens: z.number(),
    output_tokens: z.number(),
    created_at: z.string().nullable(),
  })
  .passthrough();
export type ExportedReport = z.infer<typeof ExportedReport>;

export const ExportedTrip = z
  .object({
    id: z.string(),
    destination: z.string(),
    date_start: z.string().nullable(),
    date_end: z.string().nullable(),
    budget_amount: z.number().nullable(),
    budget_currency: z.string().nullable(),
    free_text: z.string().nullable(),
    status: z.string(),
    companion_ids: z.array(z.string()),
    created_at: z.string().nullable(),
    updated_at: z.string().nullable(),
    reports: z.array(ExportedReport),
  })
  .passthrough();
export type ExportedTrip = z.infer<typeof ExportedTrip>;

export const ExportedFeedback = z
  .object({
    id: z.string(),
    trip_id: z.string(),
    card_id: z.string(),
    for_companion_id: z.string().nullable(),
    signal: z.string(),
    text: z.string().nullable(),
    created_at: z.string().nullable(),
  })
  .passthrough();
export type ExportedFeedback = z.infer<typeof ExportedFeedback>;

export const ExportPayload = z
  .object({
    generated_at: z.string(),
    user: ExportedUser,
    profile: ExportedProfile.nullable(),
    companions: z.array(ExportedCompanion),
    trips: z.array(ExportedTrip),
    feedback: z.array(ExportedFeedback),
  })
  .passthrough();
export type ExportPayload = z.infer<typeof ExportPayload>;
