"use client";

import { useSyncExternalStore } from "react";

import { useAuthStore } from "@/store/auth";

// Module-level mutable flag — flips to `true` exactly once on the client when
// `persist.rehydrate()` resolves. `useSyncExternalStore` subscribes to it so
// the value is read synchronously during render (no setState-in-effect).
let _hydrated = false;
const _listeners = new Set<() => void>();
let _rehydratePromise: Promise<unknown> | null = null;

function _kickoffRehydrate(): void {
  if (typeof window === "undefined") return;
  if (_hydrated || _rehydratePromise) return;
  // `hasHydrated` is true if the store already rehydrated (e.g. in another
  // mount); treat that as "done" without re-firing the async rehydrate.
  if (useAuthStore.persist.hasHydrated()) {
    _hydrated = true;
    _listeners.forEach((l) => l());
    return;
  }
  _rehydratePromise = Promise.resolve(useAuthStore.persist.rehydrate()).finally(() => {
    _hydrated = true;
    _listeners.forEach((l) => l());
  });
}

function _subscribe(listener: () => void): () => void {
  _kickoffRehydrate();
  _listeners.add(listener);
  return () => {
    _listeners.delete(listener);
  };
}

function _getSnapshot(): boolean {
  return _hydrated;
}

function _getServerSnapshot(): boolean {
  // SSR has no localStorage; always report "not hydrated yet" so server and
  // client first paint agree (avoids React hydration error).
  return false;
}

/**
 * Returns `true` once the zustand persist middleware has finished rehydrating
 * the auth store from localStorage. SSR-safe.
 *
 * Gate any auth-dependent UI behind this — otherwise the first client paint
 * shows the unauthenticated state for a flash even when a token is in storage.
 */
export function useHasHydrated(): boolean {
  return useSyncExternalStore(_subscribe, _getSnapshot, _getServerSnapshot);
}
