import { apiFetch, ApiError } from "@/lib/api/client";
import {
  CompanionCreateBody,
  CompanionResponse,
  CompanionsListResponse,
  CompanionUpdateBody,
  type CompanionCreateBody as CompanionCreateBodyT,
  type CompanionResponse as CompanionResponseT,
  type CompanionsListResponse as CompanionsListResponseT,
  type CompanionUpdateBody as CompanionUpdateBodyT,
} from "@/lib/schemas/companions";

/**
 * Typed 409 cases the backend returns. Callers branch on this to render
 * inline form errors (`companion_name_taken`) vs page-level banners
 * (`companion_limit_reached`). See PRD §3 + §10 R6.
 */
export type CompanionConflict = "companion_name_taken" | "companion_limit_reached";

export class CompanionConflictError extends Error {
  readonly kind: CompanionConflict;
  constructor(kind: CompanionConflict) {
    super(kind);
    this.name = "CompanionConflictError";
    this.kind = kind;
  }
}

function mapConflict(err: unknown): never {
  if (err instanceof ApiError && err.status === 409) {
    const detail = err.message;
    if (detail === "companion_name_taken" || detail === "companion_limit_reached") {
      throw new CompanionConflictError(detail);
    }
  }
  throw err;
}

export async function listCompanions(): Promise<CompanionsListResponseT> {
  const raw = await apiFetch<unknown>("/api/companions", { method: "GET" });
  return CompanionsListResponse.parse(raw);
}

export async function createCompanion(body: CompanionCreateBodyT): Promise<CompanionResponseT> {
  const validBody = CompanionCreateBody.parse(body);
  try {
    const raw = await apiFetch<unknown>("/api/companions", {
      method: "POST",
      body: JSON.stringify(validBody),
    });
    return CompanionResponse.parse(raw);
  } catch (err) {
    mapConflict(err);
  }
}

export async function updateCompanion(
  id: string,
  body: CompanionUpdateBodyT,
): Promise<CompanionResponseT> {
  const validBody = CompanionUpdateBody.parse(body);
  try {
    const raw = await apiFetch<unknown>(`/api/companions/${id}`, {
      method: "PUT",
      body: JSON.stringify(validBody),
    });
    return CompanionResponse.parse(raw);
  } catch (err) {
    mapConflict(err);
  }
}

export async function deleteCompanion(id: string): Promise<void> {
  await apiFetch<void>(`/api/companions/${id}`, { method: "DELETE" });
}
