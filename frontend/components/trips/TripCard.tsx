"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { formatTripDate } from "@/lib/format";
import { tiltStyle } from "@/lib/scrapbook/tilt";
import type { TripListItem, TripStatus } from "@/lib/schemas/trips";

const STATUS_TO_SIGNAL: Record<TripStatus, "live" | "done" | "wait" | "snag"> = {
  pending: "wait",
  clarifying: "wait",
  running: "live",
  complete: "done",
  aborted: "snag",
};

const VERDICT_BY_STATUS: Record<TripStatus, { text: string; soft: boolean }> = {
  pending: { text: "queued for the weekend", soft: true },
  clarifying: { text: "waiting on you", soft: true },
  running: { text: "still scribbling", soft: true },
  complete: { text: "pinned ★", soft: false },
  aborted: { text: "hit a wall", soft: true },
};

const TAPE_BY_INDEX = ["tape--mint", "tape--blue", "tape--yellow", "tape--red"] as const;

export interface TripCardProps {
  trip: TripListItem;
  index?: number;
}

export function TripCard({ trip, index = 0 }: TripCardProps) {
  const [label, setLabel] = useState<string>("");
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLabel(formatTripDate(trip.created_at));
  }, [trip.created_at]);

  const status = (trip.status ?? "pending") as TripStatus;
  const signal = STATUS_TO_SIGNAL[status];
  const verdict = VERDICT_BY_STATUS[status];
  const tape = TAPE_BY_INDEX[index % TAPE_BY_INDEX.length];

  return (
    <Link
      href={`/app/trips/${trip.trip_id}`}
      className="photo-card is-typed"
      style={{ ...tiltStyle(trip.trip_id), textDecoration: "none" }}
      data-trip-status={status}
    >
      <span className={`tape ${tape} cnr`} />
      <div className="photo" data-label={trip.destination} />
      <p className="cap">{trip.destination}</p>
      <p className="scrawl">
        <time dateTime={trip.created_at}>{label || " "}</time>
      </p>
      <span
        className={verdict.soft ? "verdict verdict--soft" : "verdict"}
        style={{ fontSize: 14, right: 16, bottom: 16 }}
        aria-label={verdict.text}
      >
        <span
          aria-hidden="true"
          style={{
            display: "inline-block",
            width: 7,
            height: 7,
            borderRadius: "50%",
            verticalAlign: 1,
            marginRight: 6,
            background: `hsl(var(--signal-${signal}))`,
            ...(signal === "live"
              ? { animation: "pulse 1.4s var(--ease-soft) infinite" }
              : {}),
          }}
        />
        {verdict.text}
      </span>
    </Link>
  );
}
