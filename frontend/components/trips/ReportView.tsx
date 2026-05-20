"use client";

import { PerspectiveToggle } from "@/components/trips/PerspectiveToggle";
import { ReportTabs } from "@/components/trips/ReportTabs";
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

      <PerspectiveToggle />

      <ReportTabs items={items} />
    </section>
  );
}
