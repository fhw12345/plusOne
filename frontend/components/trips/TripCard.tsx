"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { TRIP_STATUS_META, formatTripDate } from "@/lib/format";
import type { TripListItem, TripStatus } from "@/lib/schemas/trips";

function StatusBadge({ status }: { status: TripStatus }) {
  const meta = TRIP_STATUS_META[status];
  return (
    <span className={`rounded px-2 py-0.5 text-xs font-medium ${meta.classes}`}>{meta.label}</span>
  );
}

export interface TripCardProps {
  trip: TripListItem;
}

export function TripCard({ trip }: TripCardProps) {
  // Effect-mounted span so SSR renders empty and the client fills in the
  // computed relative label on hydration. Avoids React hydration mismatch
  // warnings from clock skew between server and client. PRD §8.1.
  const [label, setLabel] = useState<string>("");
  useEffect(() => {
    // The set-state-in-effect pattern is intentional here — it's the
    // documented way to defer client-only formatting past hydration.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLabel(formatTripDate(trip.created_at));
  }, [trip.created_at]);

  return (
    <li className="border-foreground/10 rounded border bg-white/50 transition hover:bg-white/80 dark:bg-black/20 dark:hover:bg-black/30">
      <Link
        href={`/app/trips/${trip.trip_id}`}
        className="flex flex-col gap-2 px-4 py-3 sm:flex-row sm:items-center sm:justify-between"
      >
        <div className="flex flex-col gap-1">
          <span className="text-base font-medium">{trip.destination}</span>
          <time dateTime={trip.created_at} className="text-foreground/60 text-xs">
            {label}
          </time>
        </div>
        <StatusBadge status={trip.status as TripStatus} />
      </Link>
    </li>
  );
}
