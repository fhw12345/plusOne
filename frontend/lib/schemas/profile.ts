import { z } from "zod";

// Zod mirrors of backend `backend/src/plus_one/api/schemas.py`. Backend uses
// `extra="forbid"` on every model; we use `.strict()` so a forgotten field
// becomes a typed error at the API boundary rather than `undefined` deep in
// a component.

export const Demographics = z
  .object({
    age_range: z.string().max(20).nullable().optional(),
    language: z.string().max(10).nullable().optional(),
  })
  .strict();
export type Demographics = z.infer<typeof Demographics>;

export const TravelStyle = z
  .object({
    budget_sensitivity: z.string().max(20).nullable().optional(),
    pace: z.string().max(20).nullable().optional(),
    comfort: z.string().max(20).nullable().optional(),
  })
  .strict();
export type TravelStyle = z.infer<typeof TravelStyle>;

export const ExplicitPreferences = z
  .object({
    loves: z.array(z.string()).max(50),
    hates: z.array(z.string()).max(50),
  })
  .strict();
export type ExplicitPreferences = z.infer<typeof ExplicitPreferences>;

export const VisitedCity = z
  .object({
    city: z.string().min(1).max(100),
    year: z.number().int().min(1900).max(2100),
    rating: z.number().int().min(1).max(5).nullable().optional(),
    feedback: z.string().max(500).nullable().optional(),
  })
  .strict();
export type VisitedCity = z.infer<typeof VisitedCity>;

export const ProfileResponse = z
  .object({
    demographics: Demographics,
    travel_style: TravelStyle,
    explicit_preferences: ExplicitPreferences,
    visited_cities: z.array(VisitedCity),
  })
  .strict();
export type ProfileResponse = z.infer<typeof ProfileResponse>;

// PUT body — same shape minus implicit_preferences (server-only). Backend
// applies defaults so a partial-looking body is legal; FE always sends the
// full object for predictable whole-document semantics.
export const ProfileUpdateBody = z
  .object({
    demographics: Demographics,
    travel_style: TravelStyle,
    explicit_preferences: ExplicitPreferences,
    visited_cities: z.array(VisitedCity).max(100),
  })
  .strict();
export type ProfileUpdateBody = z.infer<typeof ProfileUpdateBody>;
