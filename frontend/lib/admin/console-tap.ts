"use client";

import type { AuthUser } from "@/store/auth";

/**
 * Admin-only console tap. When an admin signs in we wrap the four console
 * methods so anything written to the browser console is mirrored up to the
 * backend ring buffer (visible on /admin/logs).
 *
 * Non-admins are NEVER wrapped — installAdminConsoleTap is a no-op for them
 * so we don't pay the per-call overhead on the hot path.
 */

type ConsoleLevel = "log" | "info" | "warn" | "error";

interface RingEntry {
  ts: string;
  level: ConsoleLevel;
  message: string;
}

interface InstalledState {
  user_id: string;
  originals: Record<ConsoleLevel, (...args: unknown[]) => void>;
  ring: RingEntry[];
  flushTimer: ReturnType<typeof setInterval> | null;
  inflight: boolean;
  controller: AbortController;
}

const TAP_FLAG = Symbol.for("plusOne.adminTap");
const RING_CAP = 200;
const BATCH_CAP = 50;
const FLUSH_INTERVAL_MS = 1000;
const MSG_TRUNCATE = 2000;

// Module-level singleton — exactly one install at a time.
let _state: InstalledState | null = null;

function _serialize(arg: unknown): string {
  if (typeof arg === "string") return arg;
  try {
    const seen = new WeakSet<object>();
    return JSON.stringify(arg, (_k, v) => {
      if (v && typeof v === "object") {
        if (seen.has(v as object)) return "[circular]";
        seen.add(v as object);
      }
      return v;
    });
  } catch {
    return String(arg);
  }
}

function _formatMessage(args: unknown[]): string {
  const joined = args.map(_serialize).join(" ");
  return joined.length > MSG_TRUNCATE ? joined.slice(0, MSG_TRUNCATE) + "…[truncated]" : joined;
}

async function _postBatch(entries: RingEntry[], signal: AbortSignal): Promise<void> {
  // Inline call (no apiFetch) so we don't import the auth store here and to
  // make the failure mode trivially silent — never spam the console; we ARE
  // the console.
  const base = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
  // Pull the token directly from localStorage so we don't introduce a hard
  // dependency on the auth store from this module.
  let token: string | null = null;
  try {
    const raw = window.localStorage.getItem("plus-one-auth");
    if (raw) {
      const parsed = JSON.parse(raw) as { state?: { token?: string | null } };
      token = parsed?.state?.token ?? null;
    }
  } catch {
    /* localStorage unavailable / corrupted — fall through */
  }
  await fetch(`${base}/api/admin/logs/frontend`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({ entries }),
    signal,
    credentials: "include",
  });
}

async function _flushSome(state: InstalledState): Promise<void> {
  if (state.inflight) return;
  if (state.ring.length === 0) return;
  const batch = state.ring.splice(0, BATCH_CAP);
  state.inflight = true;
  try {
    await _postBatch(batch, state.controller.signal);
  } catch {
    // Drop the batch on failure. Buffering forever would leak memory and
    // there's nowhere safe to surface the error (no toast, no console).
  } finally {
    state.inflight = false;
  }
}

function _push(state: InstalledState, level: ConsoleLevel, args: unknown[]): void {
  const entry: RingEntry = {
    ts: new Date().toISOString(),
    level,
    message: _formatMessage(args),
  };
  state.ring.push(entry);
  // Bound the ring so a runaway log loop can't OOM the page.
  if (state.ring.length > RING_CAP) {
    state.ring.splice(0, state.ring.length - RING_CAP);
  }
  // Errors flush immediately — they're the rarest and the most urgent.
  if (level === "error") {
    void _flushSome(state);
  }
}

export function installAdminConsoleTap(user: AuthUser | null): void {
  if (typeof window === "undefined") return;
  if (!user || !user.is_admin) return;

  // Already installed for the same user — no-op (idempotent across rerenders).
  // If a different user, uninstall first (admin sign-out + sign-in as another
  // admin in the same tab).
  const flag = (window as unknown as Record<symbol, string | undefined>)[TAP_FLAG];
  if (flag === user.id) return;
  if (_state) uninstallAdminConsoleTap();

  const originals: InstalledState["originals"] = {
    log: console.log.bind(console),
    info: console.info.bind(console),
    warn: console.warn.bind(console),
    error: console.error.bind(console),
  };

  const state: InstalledState = {
    user_id: user.id,
    originals,
    ring: [],
    flushTimer: null,
    inflight: false,
    controller: new AbortController(),
  };

  (["log", "info", "warn", "error"] as const).forEach((level) => {
    (console as unknown as Record<ConsoleLevel, (...args: unknown[]) => void>)[level] = (
      ...args: unknown[]
    ) => {
      originals[level](...args);
      try {
        _push(state, level, args);
      } catch {
        /* never let the tap break the page */
      }
    };
  });

  state.flushTimer = setInterval(() => {
    void _flushSome(state);
  }, FLUSH_INTERVAL_MS);

  (window as unknown as Record<symbol, string | undefined>)[TAP_FLAG] = user.id;
  _state = state;
}

export function uninstallAdminConsoleTap(): void {
  if (typeof window === "undefined") return;
  const state = _state;
  if (!state) return;
  if (state.flushTimer) clearInterval(state.flushTimer);
  state.controller.abort();
  // Restore originals.
  (["log", "info", "warn", "error"] as const).forEach((level) => {
    (console as unknown as Record<ConsoleLevel, (...args: unknown[]) => void>)[level] =
      state.originals[level];
  });
  state.ring.length = 0;
  _state = null;
  delete (window as unknown as Record<symbol, string | undefined>)[TAP_FLAG];
}
