import { z } from "zod";

// Reusable email schema with the message the e2e validation assertion matches
// (`/valid email|invalid email/i`).
export const EmailSchema = z.string().email("Please enter a valid email address.");

export const RequestLinkBody = z.object({
  email: EmailSchema,
});
export type RequestLinkBody = z.infer<typeof RequestLinkBody>;

export const ExchangeBody = z.object({
  token: z.string().min(10).max(200),
});
export type ExchangeBody = z.infer<typeof ExchangeBody>;

export const ExchangeResponse = z.object({
  access_token: z.string(),
  token_type: z.literal("bearer"),
  expires_in_minutes: z.number().int().positive(),
});
export type ExchangeResponse = z.infer<typeof ExchangeResponse>;

export const MeResponse = z.object({
  // Backend uses UUID v4 strings for user IDs.
  id: z.string().min(1),
  email: z.string().email(),
});
export type MeResponse = z.infer<typeof MeResponse>;
