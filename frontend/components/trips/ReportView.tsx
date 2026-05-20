"use client";

import type { TripDetail } from "@/lib/schemas/trips";

export interface ReportViewProps {
  trip: TripDetail;
}

export function ReportView({ trip }: ReportViewProps) {
  const items = trip.content?.items ?? [];

  return (
    <section className="flex flex-col gap-4" data-testid="report-view">
      <header className="flex items-center justify-between gap-3">
        <h2 className="text-xl font-semibold tracking-tight">Report</h2>
        <span className="border-foreground/20 rounded border px-2 py-0.5 text-xs tracking-wide uppercase">
          {trip.status}
        </span>
      </header>

      {items.length === 0 ? (
        <p className="text-foreground/70 text-sm">No results yet.</p>
      ) : (
        <ul className="flex flex-col gap-2 text-sm">
          {items.map((item, idx) => (
            <li
              key={idx}
              className="border-foreground/10 rounded border px-3 py-2 font-mono text-xs"
            >
              <pre className="break-all whitespace-pre-wrap">{JSON.stringify(item, null, 2)}</pre>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
