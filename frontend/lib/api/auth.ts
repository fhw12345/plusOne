import { apiFetch } from "@/lib/api/client";
import { ExchangeResponse, MeResponse } from "@/lib/schemas/auth";
import type {
  ExchangeResponse as ExchangeResponseT,
  MeResponse as MeResponseT,
} from "@/lib/schemas/auth";

export async function requestLink(email: string): Promise<void> {
  await apiFetch<void>("/api/auth/request-link", {
    method: "POST",
    body: JSON.stringify({ email }),
  });
}

export async function exchange(token: string): Promise<ExchangeResponseT> {
  const raw = await apiFetch<unknown>("/api/auth/exchange", {
    method: "POST",
    body: JSON.stringify({ token }),
  });
  return ExchangeResponse.parse(raw);
}

export async function me(): Promise<MeResponseT> {
  const raw = await apiFetch<unknown>("/api/auth/me", { method: "GET" });
  return MeResponse.parse(raw);
}

export async function logout(): Promise<void> {
  await apiFetch<void>("/api/auth/logout", { method: "POST" });
}
