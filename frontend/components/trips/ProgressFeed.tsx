"use client";

import type { TripEvent } from "@/lib/schemas/events";

function labelFor(event: TripEvent): string {
  switch (event.name) {
    case "started":
      return "Cycle started";
    case "iteration_start":
      return `Iteration ${event.depth + 1} starting`;
    case "producer":
      return `Generated ${event.data.n_candidates} candidates`;
    case "joiner":
      return `Joined ${event.data.n_in} → ${event.data.n_out} items`;
    case "controller": {
      const verdict = event.data.should_continue ? "continue" : "stop";
      const reasoning = event.data.reasoning ? `: ${event.data.reasoning}` : "";
      return `Decided to ${verdict}${reasoning}`;
    }
    case "cycle_aborted":
      return `Cycle aborted: ${event.data.reason}`;
    case "trip_complete":
      return `Trip ${event.status}`;
  }
}

export interface ProgressFeedProps {
  events: TripEvent[];
}

export function ProgressFeed({ events }: ProgressFeedProps) {
  return (
    <ol data-testid="progress-feed" className="flex flex-col gap-2 text-sm">
      {events.length === 0 ? (
        <li className="text-foreground/60">Waiting for first event…</li>
      ) : (
        events.map((event, idx) => (
          <li
            key={`${event.name}-${idx}`}
            className="border-foreground/10 rounded border px-3 py-2"
          >
            <span className="text-foreground/60 mr-2 font-mono text-xs">
              {event.name.replace(/_/g, " ")}
            </span>
            <span>{labelFor(event)}</span>
          </li>
        ))
      )}
    </ol>
  );
}
