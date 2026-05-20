import { apiFetch } from "@/lib/api/client";
import {
  CreateTripBody,
  CreateTripResponse,
  TripDetail,
  TripListResponse,
  type CreateTripBody as CreateTripBodyT,
  type CreateTripResponse as CreateTripResponseT,
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
