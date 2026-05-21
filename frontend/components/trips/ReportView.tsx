"use client";

import { LanguageToggle } from "@/components/trips/LanguageToggle";
import { PerspectiveToggle } from "@/components/trips/PerspectiveToggle";
import { ReportTabs } from "@/components/trips/ReportTabs";
import { useReportPrefsHasHydrated } from "@/hooks/useReportPrefsHasHydrated";
import { downloadMarkdown } from "@/lib/report/exportMarkdown";
import type { JoinedItem, TripDetail } from "@/lib/schemas/trips";
import { useReportPrefsStore, type ReportLanguage } from "@/store/reportPrefs";

export interface ReportViewProps {
  trip: TripDetail;
  readonly?: boolean;
}

function resolveItems(content: TripDetail["content"], language: ReportLanguage): JoinedItem[] {
  if (!content) return [];
  if (language === "original") return content.items ?? [];
  const translated = content.translations?.[language];
  return translated && translated.length > 0 ? translated : (content.items ?? []);
}

export function ReportView({ trip, readonly = false }: ReportViewProps) {
  const hydrated = useReportPrefsHasHydrated();
  const persistedLanguage = useReportPrefsStore((s) => s.language);
  const language: ReportLanguage = hydrated ? persistedLanguage : "original";

  const items = resolveItems(trip.content, language);

  return (
    <section
      data-testid="report-view"
      style={{
        position: "relative",
        marginTop: 12,
        padding: "30px 32px 36px",
        background: "hsl(var(--paper-2))",
        border: "1px solid hsl(var(--kraft))",
        boxShadow: "0 14px 26px -16px hsl(0 0% 0% / .22)",
      }}
    >
      <span
        className="tape tape--mint"
        style={{ top: -10, left: 36, width: 110, height: 24, transform: "rotate(-3deg)" }}
      />

      <header
        style={{
          display: "flex",
          flexWrap: "wrap",
          alignItems: "flex-end",
          justifyContent: "space-between",
          gap: 16,
          marginBottom: 18,
        }}
      >
        <div>
          <h2 className="hand-xl">the reading</h2>
          <p className="scrawl" style={{ fontSize: 15, marginTop: 4 }}>
            each card has a source. tap it open to read what the locals said.
          </p>
        </div>

        <div
          className="print:hidden"
          data-print-hide
          style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "center" }}
        >
          <button
            type="button"
            onClick={() => downloadMarkdown(trip)}
            data-testid="report-export-md"
            className="btn"
            style={{ fontSize: 18 }}
          >
            save as markdown
          </button>
          {!readonly ? (
            <button
              type="button"
              onClick={() => window.print()}
              data-testid="report-export-pdf"
              className="btn"
              style={{ fontSize: 18 }}
            >
              print
            </button>
          ) : null}
        </div>
      </header>

      <div
        className="print:hidden"
        data-print-hide
        style={{
          display: "flex",
          flexWrap: "wrap",
          alignItems: "center",
          gap: 18,
          marginBottom: 20,
          paddingBottom: 16,
          borderBottom: "1px dotted hsl(var(--kraft))",
        }}
      >
        <PerspectiveToggle />
        <LanguageToggle />
      </div>

      <ReportTabs items={items} />
    </section>
  );
}
