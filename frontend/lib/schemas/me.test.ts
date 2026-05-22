import { describe, expect, it } from "vitest";

import { ExportPayload } from "@/lib/schemas/me";

const SAMPLE = {
  generated_at: "2026-05-22T14:03:11.482Z",
  user: {
    id: "8c1f0a1e-2c0b-4f1c-9c2a-2c0b4f1c9c2a",
    email: "sara@example.com",
    username: "sara",
    is_admin: false,
    is_active: true,
    email_verified_at: "2026-04-01T08:11:00Z",
    last_login_at: "2026-05-22T13:51:08Z",
    created_at: "2026-04-01T08:10:30Z",
    updated_at: "2026-05-10T09:22:14Z",
  },
  profile: {
    demographics: { age_range: "30-39", language: "zh" },
    travel_style: { budget_sensitivity: "mid", pace: "easy", comfort: "mid" },
    explicit_preferences: { loves: ["ramen"], hates: ["queues"] },
    visited_cities: [{ city: "Tokyo", year: 2024, rating: 5 }],
  },
  companions: [
    {
      id: "11111111-1111-4111-8111-111111111111",
      name: "Wei",
      explicit_preferences: { loves: ["coffee"], hates: [] },
      constraints: {},
      created_at: "2026-04-02T10:00:00Z",
      updated_at: "2026-04-02T10:00:00Z",
    },
  ],
  trips: [
    {
      id: "22222222-2222-4222-8222-222222222222",
      destination: "Tokyo",
      date_start: "2026-09-12T00:00:00Z",
      date_end: "2026-09-20T00:00:00Z",
      budget_amount: 3200,
      budget_currency: "USD",
      free_text: "low-key",
      status: "complete",
      companion_ids: ["11111111-1111-4111-8111-111111111111"],
      created_at: "2026-05-10T08:00:00Z",
      updated_at: "2026-05-10T09:14:00Z",
      reports: [
        {
          id: "33333333-3333-4333-8333-333333333333",
          content: { tl_dr: "..." },
          input_tokens: 12450,
          output_tokens: 3890,
          created_at: "2026-05-10T09:13:55Z",
        },
      ],
    },
  ],
  feedback: [
    {
      id: "44444444-4444-4444-8444-444444444444",
      trip_id: "22222222-2222-4222-8222-222222222222",
      card_id: "tokyo-yanaka-walk",
      for_companion_id: "11111111-1111-4111-8111-111111111111",
      signal: "thumb_up",
      text: "Wei loved this",
      created_at: "2026-05-11T03:01:00Z",
    },
  ],
};

describe("ExportPayload", () => {
  it("accepts the §5 example payload", () => {
    const parsed = ExportPayload.parse(SAMPLE);
    expect(parsed.user.email).toBe("sara@example.com");
    expect(parsed.trips[0]?.reports[0]?.input_tokens).toBe(12450);
  });

  it("accepts a payload with null profile", () => {
    const out = ExportPayload.parse({ ...SAMPLE, profile: null });
    expect(out.profile).toBeNull();
  });

  it("rejects a payload missing generated_at", () => {
    const rest = { ...SAMPLE } as Partial<typeof SAMPLE>;
    delete rest.generated_at;
    expect(() => ExportPayload.parse(rest)).toThrow();
  });

  it("rejects a payload missing user", () => {
    const rest = { ...SAMPLE } as Partial<typeof SAMPLE>;
    delete rest.user;
    expect(() => ExportPayload.parse(rest)).toThrow();
  });
});
