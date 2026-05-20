"use client";

import { useSyncExternalStore } from "react";

import { useReportPrefsStore } from "@/store/reportPrefs";

// Same shape as ``useHasHydrated`` (auth store) — gates UI behind the
// reportPrefs persist rehydrate so first client paint matches SSR.
let _hydrated = false;
const _listeners = new Set<() => void>();
let _rehydratePromise: Promise<unknown> | null = null;

function _kickoffRehydrate(): void {
  if (typeof window === "undefined") return;
  if (_hydrated || _rehydratePromise) return;
  if (useReportPrefsStore.persist.hasHydrated()) {
    _hydrated = true;
    _listeners.forEach((l) => l());
    return;
  }
  _rehydratePromise = Promise.resolve(useReportPrefsStore.persist.rehydrate()).finally(() => {
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
  return false;
}

/**
 * Returns ``true`` once ``useReportPrefsStore`` has finished rehydrating
 * its persisted state from localStorage. SSR-safe; the server snapshot is
 * always ``false`` so server and first client paint agree.
 */
export function useReportPrefsHasHydrated(): boolean {
  return useSyncExternalStore(_subscribe, _getSnapshot, _getServerSnapshot);
}
