import { useAuthStore } from "@/store/auth";

/**
 * Typed error thrown by `apiFetch` on non-2xx responses. Callers can branch
 * on `status` to decide whether to surface a generic message (5xx) or a
 * field-level message (4xx with a `detail` body).
 */
export class ApiError extends Error {
  readonly status: number;
  readonly body: unknown;

  constructor(message: string, status: number, body: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

const DEFAULT_TIMEOUT_MS = 20_000;

function getApiBase(): string {
  // PRD lock: read NEXT_PUBLIC_API_URL only (no _BASE_URL alias).
  return process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
}

function shouldHandleExpiredSession(url: string): boolean {
  try {
    const path = new URL(url, getApiBase()).pathname;
    return !new Set(["/api/auth/login", "/api/auth/login-with-code"]).has(path);
  } catch {
    return true;
  }
}

function handleExpiredSession(url: string): void {
  if (!shouldHandleExpiredSession(url)) return;
  useAuthStore.getState().clear();
  if (typeof window === "undefined") return;
  if (window.location.pathname !== "/login") {
    window.location.assign("/login");
  }
}

/**
 * Thin `fetch` wrapper. JSON in / JSON out. Reads the JWT from the auth store
 * via `getState()` (not a hook — this is called from non-component code too)
 * and injects `Authorization: Bearer ...` when present.
 */
export async function apiFetch<T = unknown>(path: string, init: RequestInit = {}): Promise<T> {
  const base = getApiBase();
  const url = path.startsWith("http") ? path : `${base}${path}`;

  // Pull the token at call time so the latest value is used even if the
  // store changed between component render and the actual request.
  const token = useAuthStore.getState().token;

  const headers: Record<string, string> = {
    Accept: "application/json",
    ...(init.body !== undefined ? { "Content-Type": "application/json" } : {}),
    ...((init.headers as Record<string, string>) ?? {}),
  };
  if (token) headers.Authorization = `Bearer ${token}`;

  const controller = new AbortController();
  let timedOut = false;
  const timeout = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, DEFAULT_TIMEOUT_MS);

  const abortFromCaller = () => controller.abort(init.signal?.reason);
  if (init.signal?.aborted) abortFromCaller();
  else init.signal?.addEventListener("abort", abortFromCaller, { once: true });

  let response: Response;
  try {
    response = await fetch(url, { ...init, headers, signal: controller.signal });
  } catch (err) {
    if (timedOut) {
      throw new ApiError("request_timeout", 408, null);
    }
    throw err;
  } finally {
    clearTimeout(timeout);
    init.signal?.removeEventListener("abort", abortFromCaller);
  }

  // 204 No Content — no body to parse. Return undefined cast to T; callers
  // for 204 endpoints declare `apiFetch<void>(...)`.
  if (response.status === 204) {
    return undefined as T;
  }

  const text = await response.text();
  let parsed: unknown = undefined;
  if (text.length > 0) {
    try {
      parsed = JSON.parse(text);
    } catch {
      parsed = text;
    }
  }

  if (!response.ok) {
    const detail =
      parsed && typeof parsed === "object" && "detail" in parsed
        ? String((parsed as { detail: unknown }).detail)
        : response.statusText;
    if (response.status === 401) {
      handleExpiredSession(url);
    }
    throw new ApiError(detail, response.status, parsed);
  }

  return parsed as T;
}
