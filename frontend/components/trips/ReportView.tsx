"use client";

import { Download, Printer } from "lucide-react";

import { LanguageToggle } from "@/components/trips/LanguageToggle";
import { PerspectiveToggle } from "@/components/trips/PerspectiveToggle";
import { ReportTabs } from "@/components/trips/ReportTabs";
import { Button } from "@/components/ui/button";
import { useReportPrefsHasHydrated } from "@/hooks/useReportPrefsHasHydrated";
import { downloadMarkdown } from "@/lib/report/exportMarkdown";
import type { JoinedItem, TripDetail } from "@/lib/schemas/trips";
import { useReportPrefsStore, type ReportLanguage } from "@/store/reportPrefs";

export interface ReportViewProps {
  trip: TripDetail;
  /**
   * Hide owner-only affordances (Delete dialog is rendered by the trip
   * page itself; this prop hides the print/export buttons we render in
   * the header below). Used by `/share/[token]` for the public view.
   */
  readonly?: boolean;
}

// Resolve which items to render given the user's language preference.
// Falls back to the source-language ``content.items`` whenever the
// requested translation is missing (old reports, translator disabled,
// failed translations) so the report is never blank.
function resolveItems(content: TripDetail["content"], language: ReportLanguage): JoinedItem[] {
  if (!content) return [];
  if (language === "original") return content.items ?? [];
  const translated = content.translations?.[language];
  return translated && translated.length > 0 ? translated : (content.items ?? []);
}

export function ReportView({ trip, readonly = false }: ReportViewProps) {
  const hydrated = useReportPrefsHasHydrated();
  const persistedLanguage = useReportPrefsStore((s) => s.language);
  // Until rehydrate completes, render the SSR-default ``original`` view
  // so first client paint matches the server.
  const language: ReportLanguage = hydrated ? persistedLanguage : "original";

  const items = resolveItems(trip.content, language);

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

      <div className="flex flex-wrap items-center gap-3">
        <PerspectiveToggle />
        <LanguageToggle />
      </div>

      <ReportTabs items={items} />
    </section>
  );
}
