import { ApiError } from "@/lib/api/client";
import { useAuthStore } from "@/store/auth";

/**
 * Parse the filename out of a ``Content-Disposition: attachment; filename="..."``
 * header. Returns ``null`` when the header is missing or unparseable so
 * callers can supply a sensible fallback.
 */
export function parseFilenameFromDisposition(header: string | null): string | null {
  if (!header) return null;
  // RFC 6266 filename* is rare for our use, prioritise the simple form.
  const quoted = /filename="([^"]+)"/i.exec(header);
  if (quoted && quoted[1]) return quoted[1];
  const bare = /filename=([^;]+)/i.exec(header);
  if (bare && bare[1]) return bare[1].trim();
  return null;
}

function getApiBase(): string {
  return process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
}

function authHeader(): Record<string, string> {
  const token = useAuthStore.getState().token;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

/**
 * GET /api/me/export → triggers a browser download.
 *
 * apiFetch isn't used here because it parses JSON; we want the raw blob
 * plus the ``Content-Disposition`` header to pick up the server-suggested
 * filename.
 */
export async function exportMe(): Promise<void> {
  const response = await fetch(`${getApiBase()}/api/me/export`, {
    method: "GET",
    headers: {
      Accept: "application/json",
      ...authHeader(),
    },
  });
  if (!response.ok) {
    throw new ApiError("export_failed", response.status, null);
  }
  const blob = await response.blob();
  const filename =
    parseFilenameFromDisposition(response.headers.get("content-disposition")) ??
    `plus-one-export-${new Date().toISOString().slice(0, 10)}.json`;

  // Browser-only side effect — guarded so the function is safe to import
  // from server components.
  if (typeof window === "undefined") return;
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  URL.revokeObjectURL(url);
}

/**
 * DELETE /api/me. Throws ApiError(409, "admin_cannot_self_delete") on
 * admin self-delete attempts; the dialog renders a different message in
 * that branch. On 204 the caller is responsible for clearing the auth
 * store and navigating away.
 */
export async function deleteMe(): Promise<void> {
  const response = await fetch(`${getApiBase()}/api/me`, {
    method: "DELETE",
    headers: {
      Accept: "application/json",
      ...authHeader(),
    },
  });
  if (response.status === 204) return;
  if (response.status === 409) {
    throw new ApiError("admin_cannot_self_delete", 409, null);
  }
  if (!response.ok) {
    throw new ApiError("delete_failed", response.status, null);
  }
}
