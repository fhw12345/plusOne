"use client";

import { useTripReports } from "@/hooks/useTripReports";
import type { TripReportSummary } from "@/lib/schemas/trips";

export interface RefinementHistoryProps {
  tripId: string;
  /** The report currently rendered in the page's ReportView. Undefined =
   * latest. */
  currentReportId?: string | null;
  /** Click handler for "show this version" — caller maintains the
   * page-local report selector state. */
  onSelectReport?: (reportId: string | null) => void;
}

const HEADER = "past tweaks";
const EMPTY = "no tweaks yet. this is the original.";
const SHOW_VERSION_CTA = "show this version";
const CURRENT_MARKER = "↑ showing this one";
const ORIGINAL_LABEL = "the original";

// Render relative time like "3h ago" / "just now" without dragging in
// date-fns. Resolution is intentionally coarse — the history list isn't
// a timestamp display, it's a chronological breadcrumb.
function formatRelativeTime(iso: string, now: Date = new Date()): string {
  const then = new Date(iso).getTime();
  if (!Number.isFinite(then)) return "";
  const diffMs = now.getTime() - then;
  const sec = Math.round(diffMs / 1000);
  if (sec < 45) return "just now";
  const min = Math.round(sec / 60);
  if (min < 45) return `${min}m ago`;
  const hr = Math.round(min / 60);
  if (hr < 24) return `${hr}h ago`;
  const day = Math.round(hr / 24);
  if (day < 14) return `${day}d ago`;
  const wk = Math.round(day / 7);
  if (wk < 6) return `${wk}w ago`;
  const mo = Math.round(day / 30);
  return `${mo}mo ago`;
}

function entryLabel(report: TripReportSummary, idx: number, total: number): string {
  const version = `v${idx + 1}`;
  if (report.is_original || !report.hint) {
    return total === 1 ? ORIGINAL_LABEL : `${version} — ${ORIGINAL_LABEL}`;
  }
  // Truncate long hints — the history line is a glance, not a transcript.
  const trimmed = report.hint.length > 80 ? `${report.hint.slice(0, 77)}…` : report.hint;
  return `${version} — ${trimmed}`;
}

/**
 * Chronological list of past Report revisions for a trip. Each entry
 * is rendered as a single scrawled line; the "show this version" link
 * swaps the page's ReportView to that revision via the
 * ``onSelectReport`` callback. The currently-rendered version shows
 * the ``↑ showing this one`` marker instead of the CTA.
 *
 * Empty state (a single original report) shows the empty-state line —
 * still rendered so the surface persists across refines.
 */
export function RefinementHistory({
  tripId,
  currentReportId,
  onSelectReport,
}: RefinementHistoryProps) {
  const { data } = useTripReports(tripId);
  const reports = data?.reports ?? [];

  // Resolve "currentReportId is null/undefined" to the latest report —
  // that's the ReportView's default render when the selector is reset.
  const effectiveCurrent = currentReportId ?? reports[reports.length - 1]?.report_id ?? null;

  return (
    <section
      data-testid="refinement-history"
      style={{
        position: "relative",
        marginTop: 24,
        padding: "20px 24px 22px",
        background: "hsl(var(--paper-2))",
        border: "1px solid hsl(var(--kraft))",
        boxShadow: "0 10px 20px -16px hsl(0 0% 0% / .2)",
      }}
    >
      <span
        className="tape tape--mint"
        style={{ top: -10, left: 24, width: 80, height: 22, transform: "rotate(-2deg)" }}
      />
      <h3 className="hand-lg" style={{ fontSize: 24, marginBottom: 10 }}>
        {HEADER}
      </h3>

      {reports.length <= 1 ? (
        <p className="scrawl" data-testid="refinement-history-empty" style={{ fontSize: 15 }}>
          {EMPTY}
        </p>
      ) : (
        <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "flex", flexDirection: "column", gap: 8 }}>
          {reports.map((report, idx) => {
            const isCurrent = report.report_id === effectiveCurrent;
            const label = entryLabel(report, idx, reports.length);
            const time = formatRelativeTime(report.created_at);
            return (
              <li
                key={report.report_id}
                data-testid="refinement-history-row"
                data-current={isCurrent ? "true" : "false"}
                style={{ display: "flex", flexWrap: "wrap", alignItems: "baseline", gap: 10 }}
              >
                <span className="scrawl" style={{ fontSize: 15, flex: "1 1 auto" }}>
                  {label}
                  {time ? ` · ${time}` : ""}
                </span>
                {isCurrent ? (
                  <span
                    className="annot"
                    data-testid="refinement-history-current"
                    style={{ display: "inline-block" }}
                  >
                    {CURRENT_MARKER}
                  </span>
                ) : (
                  <button
                    type="button"
                    data-testid="refinement-history-show"
                    className="btn"
                    onClick={() => onSelectReport?.(report.report_id)}
                    style={{ fontSize: 14 }}
                  >
                    {SHOW_VERSION_CTA}
                  </button>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
