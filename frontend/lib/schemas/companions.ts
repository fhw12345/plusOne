import { z } from "zod";

import { ExplicitPreferences } from "@/lib/schemas/profile";

// Mirrors of backend `CompanionConstraints`, `CompanionResponse`, etc.
// (`backend/src/plus_one/api/schemas.py`). Uses `.strict()` to match the
// backend's `extra="forbid"`.

export const CompanionConstraints = z
  .object({
    dietary: z.array(z.string()).max(20),
    mobility: z.string().max(50).nullable().optional(),
    // km / day
    max_walking: z.number().int().min(0).max(100).nullable().optional(),
  })
  .strict();
export type CompanionConstraints = z.infer<typeof CompanionConstraints>;

export const CompanionResponse = z
  .object({
    id: z.string().uuid(),
    name: z.string().min(1).max(100),
    explicit_preferences: ExplicitPreferences,
    constraints: CompanionConstraints,
    // datetime — backend sends ISO with offset. We accept the looser
    // datetime() check (no offset required) because Pydantic may serialize
    // with or without "+00:00" depending on tz state, and we don't reason
    // about these values client-side beyond display.
    created_at: z.string().datetime({ offset: true }),
    updated_at: z.string().datetime({ offset: true }),
  })
  .strict();
export type CompanionResponse = z.infer<typeof CompanionResponse>;

export const CompanionsListResponse = z
  .object({
    companions: z.array(CompanionResponse),
  })
  .strict();
export type CompanionsListResponse = z.infer<typeof CompanionsListResponse>;

export const CompanionCreateBody = z
  .object({
    name: z.string().min(1, "Name is required").max(100),
    explicit_preferences: ExplicitPreferences,
    constraints: CompanionConstraints,
  })
  .strict();
export type CompanionCreateBody = z.infer<typeof CompanionCreateBody>;

// Backend uses an identical body for PUT (no id field). We re-export so
// callers can be explicit about intent without forcing a duplicate import.
export const CompanionUpdateBody = CompanionCreateBody;
export type CompanionUpdateBody = z.infer<typeof CompanionUpdateBody>;
