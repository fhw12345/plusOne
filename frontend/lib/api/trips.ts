import { apiFetch } from "@/lib/api/client";
import {
  ClarifyBody,
  ClarifyResponse,
  CreateShareResponse,
  CreateTripBody,
  CreateTripResponse,
  RefineTripBody,
  RefineTripResponse,
  SharedTripResponse,
  TripDetail,
  TripListResponse,
  TripReportsResponse,
  type ClarifierAnswer as ClarifierAnswerT,
  type ClarifyResponse as ClarifyResponseT,
  type CreateShareResponse as CreateShareResponseT,
  type CreateTripBody as CreateTripBodyT,
  type CreateTripResponse as CreateTripResponseT,
  type RefineTripBody as RefineTripBodyT,
  type RefineTripResponse as RefineTripResponseT,
  type SharedTripResponse as SharedTripResponseT,
  type TripDetail as TripDetailT,
  type TripListResponse as TripListResponseT,
  type TripReportsResponse as TripReportsResponseT,
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

// === Refine (batch-2u) ====================================================

/**
 * Trigger a refinement cycle on a completed trip. Returns the
 * pre-allocated report id the backend will write the new revision
 * under. The existing trip stream (keyed by trip_id) picks up the
 * new cycle's events automatically — we surface the id so callers can
 * correlate the eventual `trip_complete` event.
 */
export async function refineTrip(
  tripId: string,
  body: RefineTripBodyT,
): Promise<RefineTripResponseT> {
  const validBody = RefineTripBody.parse(body);
  const raw = await apiFetch<unknown>(`/api/trips/${tripId}/refine`, {
    method: "POST",
    body: JSON.stringify(validBody),
  });
  return RefineTripResponse.parse(raw);
}

/**
 * List the chronological history of Report revisions for a trip. The
 * first row is always the original cycle's report; subsequent rows
 * carry the `hint` that produced them.
 */
export async function listTripReports(tripId: string): Promise<TripReportsResponseT> {
  const raw = await apiFetch<unknown>(`/api/trips/${tripId}/reports`, {
    method: "GET",
  });
  return TripReportsResponse.parse(raw);
}

// === Clarifier (batch-2t) =================================================

export async function clarifyTrip(
  tripId: string,
  answers: ClarifierAnswerT[],
): Promise<ClarifyResponseT> {
  const validBody = ClarifyBody.parse({ answers });
  const raw = await apiFetch<unknown>(`/api/trips/${tripId}/clarify`, {
    method: "POST",
    body: JSON.stringify(validBody),
  });
  return ClarifyResponse.parse(raw);
}

export async function skipClarify(tripId: string): Promise<ClarifyResponseT> {
  const raw = await apiFetch<unknown>(`/api/trips/${tripId}/clarify/skip`, {
    method: "POST",
  });
  return ClarifyResponse.parse(raw);
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
