import { apiFetch } from "@/lib/api/client";
import {
  CreateShareResponse,
  CreateTripBody,
  CreateTripResponse,
  SharedTripResponse,
  TripDetail,
  TripListResponse,
  type CreateShareResponse as CreateShareResponseT,
  type CreateTripBody as CreateTripBodyT,
  type CreateTripResponse as CreateTripResponseT,
  type SharedTripResponse as SharedTripResponseT,
  type TripDetail as TripDetailT,
  type TripListResponse as TripListResponseT,
} from "@/lib/schemas/trips";

export async function createTrip(body: CreateTripBodyT): Promise<CreateTripResponseT> {
  // Validate outgoing body so a bad call site fails loudly here, not at the
  // network boundary.
  const validBody = CreateTripBody.parse(body);
  const raw = await apiFetch<unknown>("/api/trips", {
    method: "POST",
    body: JSON.stringify(validBody),
  });
  return CreateTripResponse.parse(raw);
}

export async function getTrip(id: string): Promise<TripDetailT> {
  const raw = await apiFetch<unknown>(`/api/trips/${id}`, { method: "GET" });
  return TripDetail.parse(raw);
}

export interface ListTripsParams {
  limit?: number;
  cursor?: string | null;
}

export async function listTrips(params: ListTripsParams = {}): Promise<TripListResponseT> {
  const search = new URLSearchParams();
  if (params.limit !== undefined) search.set("limit", String(params.limit));
  if (params.cursor) search.set("cursor", params.cursor);
  const qs = search.toString();
  const path = qs ? `/api/trips?${qs}` : "/api/trips";
  const raw = await apiFetch<unknown>(path, { method: "GET" });
  return TripListResponse.parse(raw);
}

// === Share / Delete =======================================================

export async function createShare(tripId: string): Promise<CreateShareResponseT> {
  const raw = await apiFetch<unknown>(`/api/trips/${tripId}/share`, { method: "POST" });
  return CreateShareResponse.parse(raw);
}

export async function revokeShare(tripId: string, token: string): Promise<void> {
  await apiFetch<void>(`/api/trips/${tripId}/share/${encodeURIComponent(token)}`, {
    method: "DELETE",
  });
}

export async function deleteTrip(tripId: string): Promise<void> {
  await apiFetch<void>(`/api/trips/${tripId}`, { method: "DELETE" });
}

/**
 * Fetch a shared trip by its public token. Does **not** require an auth
 * token — the route is callable from a logged-out browser or a server
 * component without forwarding cookies.
 */
export async function getSharedTrip(token: string): Promise<SharedTripResponseT> {
  const base = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
  const response = await fetch(`${base}/api/shared/${encodeURIComponent(token)}`, {
    method: "GET",
    headers: { Accept: "application/json" },
    cache: "no-store",
  });
  if (response.status === 404) {
    return Promise.reject(new Error("share_not_found_or_expired"));
  }
  if (!response.ok) {
    return Promise.reject(new Error(`share_fetch_failed_${response.status}`));
  }
  const raw = (await response.json()) as unknown;
  return SharedTripResponse.parse(raw);
}
