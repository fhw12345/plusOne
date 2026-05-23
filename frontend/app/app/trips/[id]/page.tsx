"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { ProgressFeed } from "@/components/trips/ProgressFeed";
import { RefinePanel } from "@/components/trips/RefinePanel";
import { RefinementHistory } from "@/components/trips/RefinementHistory";
import { ReportView } from "@/components/trips/ReportView";
import { ItineraryView } from "@/components/trips/ItineraryView";
import { DeleteTripDialog } from "@/components/trips/DeleteTripDialog";
import { ShareDialog } from "@/components/trips/ShareDialog";
import { AdminWireLink } from "@/components/AdminWireLink";
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

const STAMP_BY_STATUS: Record<DerivedStatus, { word: string; tone: string }> = {
  running: { word: "scribbling", tone: "hsl(var(--red))" },
  complete: { word: "pinned", tone: "hsl(var(--signal-done))" },
  aborted: { word: "hit a wall", tone: "hsl(var(--signal-snag))" },
};

export default function TripDetailPage() {
  const hydrated = useHasHydrated();
  const router = useRouter();
  const token = useAuthStore((s) => s.token);
  const params = useParams<{ id: string }>();
  const tripId = params?.id ?? null;
  const qc = useQueryClient();
  // Local-only selector for which Report revision the ReportView renders.
  // ``null`` = follow the latest (default). Reset whenever a fresh
  // trip_complete event lands so a refine snaps back to the new active.
  const [shownReportId, setShownReportId] = useState<string | null>(null);

  useEffect(() => {
    if (hydrated && !token) {
      router.replace("/login");
    }
  }, [hydrated, token, router]);

  const ready = hydrated && !!token;
  const stream = useTripStream(ready ? tripId : null);
  const { data: trip, refetch } = useTrip(ready ? tripId : null);

  const fromEvents = useMemo(() => deriveStatusFromEvents(stream.events), [stream.events]);
  const fromTrip: DerivedStatus | null =
    trip?.status === "complete" || trip?.status === "aborted" ? trip.status : null;
  const derived: DerivedStatus = fromEvents ?? fromTrip ?? "running";
  const terminal = derived !== "running";

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

  useEffect(() => {
    if (fromEvents) {
      refetch();
      // Batch-2u: a fresh trip_complete (initial or refine) invalidates the
      // revision list so RefinementHistory picks up the new row.
      if (tripId) {
        qc.invalidateQueries({ queryKey: ["trip-reports", tripId] });
      }
    }
  }, [fromEvents, refetch, qc, tripId]);

  // Track the most recent trip_complete count; whenever it ticks up
  // (e.g. a refine just landed) we want to reset the local report
  // selector back to "follow latest" without using setState-in-effect.
  // The render-time setState pattern is what React 19's `react-hooks/
  // set-state-in-effect` lint rule asks us to use here.
  const completeCount = stream.events.reduce((n, e) => (e.name === "trip_complete" ? n + 1 : n), 0);
  const [lastSeenCompleteCount, setLastSeenCompleteCount] = useState(completeCount);
  if (completeCount !== lastSeenCompleteCount) {
    setLastSeenCompleteCount(completeCount);
    if (shownReportId !== null) setShownReportId(null);
  }

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
      document.title = trip?.destination ? `Plus One — ${trip.destination}` : "Plus One — reading";
    }
  }, [trip?.destination]);

  if (!ready) {
    return (
      <div className="shell">
        <p className="scrawl" style={{ marginTop: 80, fontSize: 19 }}>
          one sec &mdash; opening the reading&hellip;
        </p>
      </div>
    );
  }

  const stamp = STAMP_BY_STATUS[derived];

  return (
    <div className="shell" data-trip-status={derived} style={{ maxWidth: 1100 }}>
      <nav className="nav-strip" style={{ marginBottom: 32 }}>
        <p className="crest" style={{ marginRight: "auto" }}>
          <span className="crest-dot" />
          PLUS &middot; ONE
        </p>
        <Link href="/app">your readings</Link>
        <span className="sep" />
        <Link href="/app/trips/new" title="plan a new trip">
          new reading
        </Link>
        <span className="sep" />
        <Link href="/app/companions">who you bring</Link>
        <span className="sep" />
        <Link href="/app/profile">about you</Link>
        <AdminWireLink />
      </nav>

      <header style={{ position: "relative", padding: "12px 0 32px" }}>
        <span
          className="tape tape--blue"
          style={{ top: -8, left: 200, width: 96, height: 24, transform: "rotate(-2deg)" }}
        />
        <h1 className="hand-xxl">{trip?.destination ?? "your reading"}</h1>
        <p className="scrawl" style={{ fontSize: 19, maxWidth: 580, marginTop: 14 }}>
          {derived === "running"
            ? "i'm out asking around. you can watch me think below."
            : derived === "complete"
              ? "here's what i found. each card has a source so you can verify."
              : "couldn't finish this one. the bits i did pull are below."}
        </p>

        <span
          className="stamp"
          style={{ position: "absolute", top: 18, right: 0, color: stamp.tone }}
        >
          {stamp.word}
          <span className="ymd">{trip?.destination ?? "reading"}</span>
        </span>
      </header>

      {terminal && trip ? (
        <div
          className="print:hidden"
          data-print-hide
          style={{ display: "flex", flexWrap: "wrap", gap: 12, marginBottom: 24 }}
        >
          <ShareDialog tripId={trip.trip_id} />
          <DeleteTripDialog tripId={trip.trip_id} status={trip.status} />
        </div>
      ) : null}

      {stream.status === "error" && stream.lastError && !terminal ? (
        <div
          role="alert"
          className="ticket"
          style={{ marginBottom: 24, ["--tilt" as never]: "-.6deg" }}
        >
          <div className="stamp-row">
            <span className="type" style={{ color: "hsl(var(--signal-snag))" }}>
              wire cut
            </span>
            <span className="type-sm">{stream.lastError}</span>
          </div>
          <p className="body">
            the live channel dropped. i&rsquo;ll keep checking in case the notebook syncs later.
          </p>
        </div>
      ) : null}

      <section
        style={{
          position: "relative",
          padding: "26px 28px 30px",
          background: "hsl(var(--paper-2))",
          border: "1px solid hsl(var(--kraft))",
          boxShadow: "0 12px 24px -16px hsl(0 0% 0% / .22)",
          marginBottom: 36,
        }}
      >
        <span
          className="tape tape--yellow"
          style={{ top: -10, left: 24, width: 120, height: 24, transform: "rotate(-3deg)" }}
        />
        <p className="type" style={{ marginBottom: 18 }}>
          field log
        </p>
        <ProgressFeed events={feedEvents} destination={trip?.destination} />
      </section>

      {terminal && trip ? (
        trip.content?.day_plan && trip.content.day_plan.length > 0 ? (
          <ItineraryView trip={trip} />
        ) : (
          <ReportView trip={trip} />
        )
      ) : null}
      {derived === "complete" && trip ? (
        <>
          <RefinePanel tripId={trip.trip_id} disabled={derived !== "complete"} />
          <RefinementHistory
            tripId={trip.trip_id}
            currentReportId={shownReportId}
            onSelectReport={setShownReportId}
          />
        </>
      ) : null}

      <footer style={{ marginTop: 80, paddingTop: 18, borderTop: "1px dotted hsl(var(--kraft))" }}>
        <p className="type">
          PLUS &middot; ONE &middot; {trip?.destination ?? "reading"} &middot; v0.1
        </p>
      </footer>
    </div>
  );
}
