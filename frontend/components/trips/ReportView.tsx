"use client";

import { useMemo } from "react";

import { LanguageToggle } from "@/components/trips/LanguageToggle";
import { PerspectiveToggle } from "@/components/trips/PerspectiveToggle";
import { ReportTabs } from "@/components/trips/ReportTabs";
import { useCompanions } from "@/hooks/useCompanions";
import { useCurrentUser } from "@/hooks/useCurrentUser";
import { useReportPrefsHasHydrated } from "@/hooks/useReportPrefsHasHydrated";
import { downloadMarkdown } from "@/lib/report/exportMarkdown";
import type { JoinedItem, TripDetail } from "@/lib/schemas/trips";
import type { Party } from "@/lib/trips/categorize";
import { useReportPrefsStore, type ReportLanguage } from "@/store/reportPrefs";

export interface ReportViewProps {
  trip: TripDetail;
  readonly?: boolean;
}

function resolveItems(content: TripDetail["content"], language: ReportLanguage): JoinedItem[] {
  if (!content) return [];
  if (language === "original") return content.items ?? [];
  const translated = content.translations?.[language];
  if (!translated) return content.items ?? [];
  // Batch-2q widened the translations shape: legacy is a bare array; new
  // is `{items, tl_dr}`. Accept both.
  const items = Array.isArray(translated) ? translated : translated.items;
  return items && items.length > 0 ? items : (content.items ?? []);
}

function resolveTlDr(content: TripDetail["content"], language: ReportLanguage): string | null {
  if (!content) return null;
  if (language === "original") return content.tl_dr ?? null;
  const translated = content.translations?.[language];
  if (translated && !Array.isArray(translated) && translated.tl_dr) return translated.tl_dr;
  return content.tl_dr ?? null;
}

export function ReportView({ trip, readonly = false }: ReportViewProps) {
  const hydrated = useReportPrefsHasHydrated();
  const persistedLanguage = useReportPrefsStore((s) => s.language);
  const language: ReportLanguage = hydrated ? persistedLanguage : "original";

  const items = resolveItems(trip.content, language);
  const tlDr = resolveTlDr(trip.content, language);

  // Batch-2p: thread the party + label map through to the tabs / cards.
  // We pull the user from ``useCurrentUser`` (to label their own row as
  // ``you``) and companion names from ``useCompanions`` so the match line
  // reads e.g. ``match  you: 0.8 · alice: 0.3``. Both hooks are gated on
  // auth — on the shared / public endpoint they return ``undefined`` and
  // the match line silently hides (matches the design's "no signal worth
  // showing" rule for ownerless reports).
  const { data: currentUser } = useCurrentUser();
  const { data: companions } = useCompanions();
  const party: Party | null = trip.party
    ? { user_id: trip.party.user_id, companion_ids: trip.party.companion_ids }
    : null;
  const partyNames = useMemo(() => {
    const map: Record<string, string> = {};
    if (currentUser?.id) {
      map[currentUser.id] = currentUser.username ?? "you";
    }
    for (const c of companions?.companions ?? []) {
      map[c.id] = c.name;
    }
    return map;
  }, [currentUser, companions]);

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

      {tlDr ? (
        <aside
          data-testid="report-tldr"
          style={{
            position: "relative",
            margin: "0 0 22px",
            padding: "18px 22px 20px",
            background: "hsl(var(--paper-3))",
            border: "1px solid hsl(var(--kraft))",
            transform: "rotate(-0.3deg)",
          }}
        >
          <span
            className="tape tape--yellow"
            style={{ top: -10, right: 36, width: 90, height: 22, transform: "rotate(2deg)" }}
          />
          <p className="scrawl" style={{ fontSize: 17, lineHeight: 1.55, margin: 0 }}>
            {tlDr}
          </p>
        </aside>
      ) : null}

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

      <ReportTabs items={items} party={party} partyNames={partyNames} />
    </section>
  );
}
