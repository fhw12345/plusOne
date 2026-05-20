"use client";

import { Download, Printer } from "lucide-react";

import { PerspectiveToggle } from "@/components/trips/PerspectiveToggle";
import { ReportTabs } from "@/components/trips/ReportTabs";
import { Button } from "@/components/ui/button";
import { downloadMarkdown } from "@/lib/report/exportMarkdown";
import type { TripDetail } from "@/lib/schemas/trips";

export interface ReportViewProps {
  trip: TripDetail;
  /**
   * Hide owner-only affordances (Delete dialog is rendered by the trip
   * page itself; this prop hides the print/export buttons we render in
   * the header below). Used by `/share/[token]` for the public view.
   */
  readonly?: boolean;
}

export function ReportView({ trip, readonly = false }: ReportViewProps) {
  const items = trip.content?.items ?? [];

  return (
    <section className="flex flex-col gap-4" data-testid="report-view">
      <header className="flex items-center justify-between gap-3">
        <h2 className="text-xl font-semibold tracking-tight">Report</h2>
        <div className="flex items-center gap-2">
          <span className="border-foreground/20 rounded border px-2 py-0.5 text-xs tracking-wide uppercase">
            {trip.status}
          </span>
          {/* Markdown export is safe on the public read-only page too —
              it only reads data already on the page. */}
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={() => downloadMarkdown(trip)}
            data-testid="report-export-md"
            data-print-hide
            className="print:hidden"
          >
            <Download className="h-4 w-4" />
            Markdown
          </Button>
          {!readonly ? (
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={() => window.print()}
              data-testid="report-export-pdf"
              data-print-hide
              className="print:hidden"
            >
              <Printer className="h-4 w-4" />
              PDF
            </Button>
          ) : null}
        </div>
      </header>

      <PerspectiveToggle />

      <ReportTabs items={items} />
    </section>
  );
}
