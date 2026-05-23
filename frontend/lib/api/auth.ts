import { apiFetch } from "@/lib/api/client";
import { MeResponse, RegisterResponse, TokenResponse } from "@/lib/schemas/auth";
import type {
  MeResponse as MeResponseT,
  RegisterResponse as RegisterResponseT,
  TokenResponse as TokenResponseT,
} from "@/lib/schemas/auth";

/**
 * POST /api/auth/register — start the sign-up flow. The backend writes the
 * user row (unverified) and sends a verify_email code over SMTP. Caller
 * should then router.push to `/verify?email=...`.
 */
export async function register(body: {
  username: string;
  email: string;
  password: string;
}): Promise<RegisterResponseT> {
  const raw = await apiFetch<unknown>("/api/auth/register", {
    method: "POST",
    body: JSON.stringify(body),
  });
  return RegisterResponse.parse(raw);
}

/**
 * POST /api/auth/verify — consume a verify_email code, set
 * users.email_verified_at, and mint a JWT in one shot. Returns the same
 * token shape as /login.
 */
export async function verify(body: { email: string; code: string }): Promise<TokenResponseT> {
  const raw = await apiFetch<unknown>("/api/auth/verify", {
    method: "POST",
    body: JSON.stringify(body),
  });
  return TokenResponse.parse(raw);
}

/**
 * POST /api/auth/login — password sign-in. `identifier` may be the username
 * OR the email; the backend detects which by the presence of `@`.
 */
export async function login(body: {
  identifier: string;
  password: string;
}): Promise<TokenResponseT> {
  const raw = await apiFetch<unknown>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify(body),
  });
  return TokenResponse.parse(raw);
}

/**
 * POST /api/auth/request-code — ask for a 6-digit code by email. Rate-limited
 * to 1/60s server-side. Always returns 204 (no enumeration). The backend
 * picks the purpose: verify_email for unverified users, login for verified.
 */
export async function requestCode(body: { email: string }): Promise<void> {
  await apiFetch<void>("/api/auth/request-code", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/**
 * POST /api/auth/login-with-code — consume a `login` code and mint a JWT.
 */
export async function loginWithCode(body: {
  email: string;
  code: string;
}): Promise<TokenResponseT> {
  const raw = await apiFetch<unknown>("/api/auth/login-with-code", {
    method: "POST",
    body: JSON.stringify(body),
  });
  return TokenResponse.parse(raw);
}

/**
 * GET /api/auth/me — current user shape, now including `username` and
 * `is_admin` (added in batch-2m).
 */
export async function me(): Promise<MeResponseT> {
  const raw = await apiFetch<unknown>("/api/auth/me", { method: "GET" });
  return MeResponse.parse(raw);
}

/**
 * POST /api/auth/logout — clears the httpOnly cookie server-side. Caller is
 * responsible for clearing the zustand auth store.
 */
export async function logout(): Promise<void> {
  await apiFetch<void>("/api/auth/logout", { method: "POST" });
}
