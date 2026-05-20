"use client";

import { useParams, useRouter } from "next/navigation";
import { useEffect, useMemo } from "react";

import { ProgressFeed } from "@/components/trips/ProgressFeed";
import { ReportView } from "@/components/trips/ReportView";
import { useHasHydrated } from "@/hooks/useHasHydrated";
import { useTrip } from "@/hooks/useTrip";
import { useTripStream } from "@/hooks/useTripStream";
import type { TripEvent } from "@/lib/schemas/events";
import { useAuthStore } from "@/store/auth";

type DerivedStatus = "running" | "complete" | "aborted";

function deriveStatusFromEvents(events: TripEvent[]): DerivedStatus | null {
  for (let i = events.length - 1; i >= 0; i--) {
    const ev = events[i];
    if (!ev) continue;
    if (ev.name === "trip_complete") {
      return ev.status === "aborted" ? "aborted" : "complete";
    }
    if (ev.name === "cycle_aborted") {
      return "aborted";
    }
  }
  return null;
}

export default function TripDetailPage() {
  const hydrated = useHasHydrated();
  const router = useRouter();
  const token = useAuthStore((s) => s.token);
  const params = useParams<{ id: string }>();
  const tripId = params?.id ?? null;

  useEffect(() => {
    if (hydrated && !token) {
      router.replace("/login");
    }
  }, [hydrated, token, router]);

  const ready = hydrated && !!token;
  const stream = useTripStream(ready ? tripId : null);
  const { data: trip, refetch } = useTrip(ready ? tripId : null);

  // Derive status from events first (live source of truth); fall back to the
  // persisted Trip row if no terminal event has arrived. This covers two cases:
  // (a) the page is opened after the cycle already finished — the per-trip
  //     queue is dropped by then so SSE errors immediately with no events;
  // (b) SSE errors mid-cycle but the trip later persists a terminal state.
  const fromEvents = useMemo(() => deriveStatusFromEvents(stream.events), [stream.events]);
  const fromTrip: DerivedStatus | null =
    trip?.status === "complete" || trip?.status === "aborted" ? trip.status : null;
  const derived: DerivedStatus = fromEvents ?? fromTrip ?? "running";
  const terminal = derived !== "running";

  // If the SSE stream produced no events at all but the trip has reached a
  // terminal state (covered above), surface a synthetic terminal event in
  // the feed so the user — and the e2e contract — sees the outcome. Live
  // events always win when they arrive.
  const feedEvents = useMemo<TripEvent[]>(() => {
    if (stream.events.length > 0) return stream.events;
    if (fromTrip && trip) {
      return [
        {
          name: "trip_complete",
          trip_id: trip.trip_id,
          status: fromTrip,
        },
      ];
    }
    return [];
  }, [stream.events, fromTrip, trip]);

  // Refetch on terminal-from-events transition so the latest report content
  // is fresh when ReportView renders.
  useEffect(() => {
    if (fromEvents) {
      refetch();
    }
  }, [fromEvents, refetch]);

  // If the stream errored without ever producing events, poll the trip
  // endpoint until it reaches a terminal status. Covers case (a) above.
  useEffect(() => {
    if (!ready || !tripId) return;
    if (stream.status !== "error") return;
    if (fromEvents) return;
    if (terminal) return;
    const t = setInterval(() => refetch(), 1500);
    return () => clearInterval(t);
  }, [ready, tripId, stream.status, fromEvents, terminal, refetch]);

  useEffect(() => {
    if (typeof document !== "undefined") {
      document.title = "Trip · Plus One";
    }
  }, []);

  if (!ready) {
    return (
      <main className="mx-auto flex min-h-screen max-w-2xl flex-col items-center justify-center p-6">
        <p className="text-muted-foreground text-sm">Loading…</p>
      </main>
    );
  }

  return (
    <main
      data-trip-status={derived}
      className="mx-auto flex min-h-screen max-w-2xl flex-col gap-6 p-6"
    >
      <header>
        <h1 className="text-2xl font-bold tracking-tight">
          Trip {trip?.destination ? `— ${trip.destination}` : ""}
        </h1>
        <p className="text-foreground/70 mt-1 text-sm">Live progress and final report.</p>
      </header>

      {stream.status === "error" && stream.lastError && !terminal ? (
        <p role="alert" className="text-sm text-red-600">
          {stream.lastError}
        </p>
      ) : null}

      <section className="flex flex-col gap-2">
        <h2 className="text-sm font-semibold tracking-wide uppercase">Progress</h2>
        <ProgressFeed events={feedEvents} />
      </section>

      {terminal && trip ? <ReportView trip={trip} /> : null}
    </main>
  );
}
