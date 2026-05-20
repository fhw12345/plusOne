import { apiFetch } from "@/lib/api/client";
import {
  ProfileResponse,
  ProfileUpdateBody,
  type ProfileResponse as ProfileResponseT,
  type ProfileUpdateBody as ProfileUpdateBodyT,
} from "@/lib/schemas/profile";

export async function getProfile(): Promise<ProfileResponseT> {
  const raw = await apiFetch<unknown>("/api/profile", { method: "GET" });
  return ProfileResponse.parse(raw);
}

export async function updateProfile(body: ProfileUpdateBodyT): Promise<ProfileResponseT> {
  // Validate outgoing body so a bad call site fails loudly here, not at the
  // network boundary.
  const validBody = ProfileUpdateBody.parse(body);
  const raw = await apiFetch<unknown>("/api/profile", {
    method: "PUT",
    body: JSON.stringify(validBody),
  });
  return ProfileResponse.parse(raw);
}
