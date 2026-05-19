import { apiFetch } from "@/lib/api/client";
import {
  CreateTripBody,
  CreateTripResponse,
  TripDetail,
  type CreateTripBody as CreateTripBodyT,
  type CreateTripResponse as CreateTripResponseT,
  type TripDetail as TripDetailT,
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
