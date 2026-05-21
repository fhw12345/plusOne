"use client";

import { useMemo } from "react";

import type { TripEvent } from "@/lib/schemas/events";
import { heartbeatLine, voiceFor } from "@/lib/scrapbook/voice";

export interface ProgressFeedProps {
  events: TripEvent[];
  destination?: string;
}

interface RenderedLine {
  key: string;
  text: string;
  signal: "live" | "done" | "wait" | "snag";
  isTerminal: boolean;
}

function eventSignal(event: TripEvent): RenderedLine["signal"] {
  switch (event.name) {
    case "started":
    case "iteration_start":
    case "producer":
      return "live";
    case "joiner":
    case "controller":
      return "wait";
    case "trip_complete":
      return event.status === "aborted" ? "snag" : "done";
    case "cycle_aborted":
      return "snag";
  }
}

export function ProgressFeed({ events, destination }: ProgressFeedProps) {
  // Per-event round-robin index so the voice pool doesn't repeat in one cycle.
  const lines = useMemo<RenderedLine[]>(() => {
    const counters: Record<string, number> = {};
    return events.map((event, idx) => {
      counters[event.name] = (counters[event.name] ?? 0) + 1;
      const occurrence = (counters[event.name] ?? 1) - 1;
      const { line } = voiceFor(event, occurrence, { destination });
      return {
        key: `${event.name}-${idx}`,
        text: line || heartbeatLine(idx),
        signal: eventSignal(event),
        isTerminal: event.name === "trip_complete" || event.name === "cycle_aborted",
      };
    });
  }, [events, destination]);

  return (
    <ol
      data-testid="progress-feed"
      className="progress-feed"
      style={{ listStyle: "none", padding: 0, margin: 0, display: "grid", gap: 14 }}
    >
      {lines.length === 0 ? (
        <li className="scrawl" style={{ fontSize: 16, color: "hsl(var(--ink-3))" }}>
          <span
            aria-hidden="true"
            style={{
              display: "inline-block",
              width: 7,
              height: 7,
              marginRight: 8,
              borderRadius: "50%",
              background: "hsl(var(--signal-wait))",
              verticalAlign: 1,
            }}
          />
          warming up&hellip;
        </li>
      ) : (
        lines.map((line) => (
          <li
            key={line.key}
            className="hand"
            data-event-signal={line.signal}
            style={{
              position: "relative",
              paddingLeft: 22,
              fontSize: 20,
              lineHeight: 1.32,
              color: "hsl(var(--ink))",
            }}
          >
            <span
              aria-hidden="true"
              style={{
                position: "absolute",
                left: 0,
                top: 10,
                width: 9,
                height: 9,
                borderRadius: "50%",
                background: `hsl(var(--signal-${line.signal}))`,
                ...(line.signal === "live"
                  ? { animation: "pulse 1.4s var(--ease-soft) infinite" }
                  : {}),
              }}
            />
            {line.text}
          </li>
        ))
      )}
    </ol>
  );
}
