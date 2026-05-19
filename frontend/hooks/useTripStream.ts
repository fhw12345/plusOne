"use client";

import { useEffect, useState, useSyncExternalStore } from "react";

import type { TripEvent } from "@/lib/schemas/events";
import { openTripStream, type TripStreamHandle } from "@/lib/sse";
import { useAuthStore } from "@/store/auth";

export type TripStreamStatus = "connecting" | "open" | "closed" | "error";

export interface UseTripStreamResult {
  events: TripEvent[];
  status: TripStreamStatus;
  lastError: string | null;
}

interface StreamSnapshot {
  events: TripEvent[];
  status: TripStreamStatus;
  lastError: string | null;
}

const EMPTY_SNAPSHOT: StreamSnapshot = {
  events: [],
  status: "connecting",
  lastError: null,
};

// One bus per active tripId. Keyed map keeps multiple subscribers in sync
// without each opening its own EventSource. v1 only mounts one detail page
// at a time so the map usually has 0-1 entries.
class TripStreamBus {
  private snapshot: StreamSnapshot = EMPTY_SNAPSHOT;
  private listeners = new Set<() => void>();
  private handle: TripStreamHandle | null = null;
  private refcount = 0;

  constructor(
    public readonly tripId: string,
    private readonly onDispose: () => void,
  ) {}

  subscribe(listener: () => void): () => void {
    this.refcount += 1;
    if (this.refcount === 1) {
      this.connect();
    }
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
      this.refcount -= 1;
      if (this.refcount === 0) {
        this.disconnect();
      }
    };
  }

  getSnapshot(): StreamSnapshot {
    return this.snapshot;
  }

  private connect(): void {
    if (typeof window === "undefined") return;
    const token = useAuthStore.getState().token;
    if (!token) {
      this.replace({
        events: [],
        status: "error",
        lastError: "No auth token; please sign in again.",
      });
      return;
    }
    this.replace({ events: [], status: "open", lastError: null });
    this.handle = openTripStream(this.tripId, token, {
      onEvent: (event) => {
        this.replace({ ...this.snapshot, events: [...this.snapshot.events, event] });
      },
      onError: () => {
        this.replace({
          ...this.snapshot,
          status: "error",
          lastError: "Connection lost. Please refresh.",
        });
      },
      onClose: () => {
        if (this.snapshot.status !== "error") {
          this.replace({ ...this.snapshot, status: "closed" });
        }
      },
    });
  }

  private disconnect(): void {
    this.handle?.close();
    this.handle = null;
    this.onDispose();
  }

  private replace(next: StreamSnapshot): void {
    this.snapshot = next;
    for (const l of this.listeners) l();
  }
}

const _buses = new Map<string, TripStreamBus>();

function getOrCreateBus(tripId: string): TripStreamBus {
  let bus = _buses.get(tripId);
  if (!bus) {
    bus = new TripStreamBus(tripId, () => {
      _buses.delete(tripId);
    });
    _buses.set(tripId, bus);
  }
  return bus;
}

// v1 cycles emit O(10) events. Appending to state on every frame is fine
// at that order. If a future protocol streams hundreds-of-events runs, this
// hook will need batching (e.g. RAF flush) — comment kept here so future-us
// notices before flooding React.
//
// Lifecycle invariant: the EventSource is closed (a) when the component
// unmounts (via useSyncExternalStore's unsubscribe → refcount→0 → disconnect)
// and (b) when the stream errors (onError calls close()). (b) disables
// EventSource's native auto-reconnect, which would otherwise loop on a 401
// (token expired mid-cycle is rare — 60min TTL vs ~60-90s cycle — but
// possible). trip_runner.py:280-289 publishes trip_complete AFTER the
// report is committed, so by the time the SSE frame reaches us the row is
// durable.
export function useTripStream(tripId: string | null): UseTripStreamResult {
  // useSyncExternalStore demands stable subscribe / getSnapshot identities
  // per tripId. Keep them in state, rebuilt only when tripId changes.
  const [{ subscribe, getSnapshot, getServerSnapshot }, setSubs] = useState(() =>
    buildSubs(tripId),
  );
  const [currentId, setCurrentId] = useState(tripId);
  if (currentId !== tripId) {
    setCurrentId(tripId);
    setSubs(buildSubs(tripId));
  }

  const snapshot = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
  // Reset any module-level state when the hook unmounts entirely (handled
  // automatically by the bus refcount). Effect kept for symmetry / future
  // teardown hooks.
  useEffect(() => () => void 0, []);
  return snapshot;
}

function buildSubs(tripId: string | null) {
  if (!tripId) {
    return {
      subscribe: (_l: () => void) => () => {},
      getSnapshot: () => EMPTY_SNAPSHOT,
      getServerSnapshot: () => EMPTY_SNAPSHOT,
    };
  }
  return {
    subscribe: (listener: () => void) => getOrCreateBus(tripId).subscribe(listener),
    getSnapshot: () => getOrCreateBus(tripId).getSnapshot(),
    getServerSnapshot: () => EMPTY_SNAPSHOT,
  };
}
