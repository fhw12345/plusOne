"use client";

import type { CSSProperties } from "react";

import { LanguageToggle } from "@/components/trips/LanguageToggle";
import { PerspectiveToggle } from "@/components/trips/PerspectiveToggle";
import type {
  DayPlan as DayPlanT,
  DaySlot as DaySlotT,
  JoinedItem,
  JoinedItemView,
  TripDetail,
} from "@/lib/schemas/trips";
import { TAB_LABELS, TAB_ORDER } from "@/lib/trips/categorize";

export interface ItineraryViewProps {
  trip: TripDetail;
}

const PERIOD_ORDER: DaySlotT["period"][] = ["morning", "afternoon", "evening", "late_night"];

const PERIOD_LABEL: Record<DaySlotT["period"], string> = {
  morning: "morning",
  afternoon: "afternoon",
  evening: "evening",
  late_night: "late night",
};

// Mirrors ItemCard's VERDICT_BY_CLASS (text + signal) but tuned to the
// itinerary mockup's shorter phrasing ("go." / "skip." etc.).
const VERDICT_BY_CLASS: Record<string, { text: string; signal: "done" | "snag" | "wait" }> = {
  local_gem: { text: "go.", signal: "done" },
  tourist_trap: { text: "skip.", signal: "snag" },
  neutral: { text: "okay-ish.", signal: "wait" },
  insufficient: { text: "thin signal.", signal: "wait" },
};

const TAPE_BY_INDEX = ["tape--mint", "tape--blue", "tape--yellow", "tape--red"] as const;

/**
 * PRD batch-3a — day-by-day itinerary surface. Rendered in place of
 * ``<ReportView>`` when ``trip.content.day_plan`` is non-empty. Items
 * are resolved by ``slot.item_index`` into ``trip.content.items``;
 * missing indices render nothing (scheduler validation should prevent
 * this, but the frontend stays defensive).
 */
export function ItineraryView({ trip }: ItineraryViewProps) {
  const items = trip.content?.items ?? [];
  const days = trip.content?.day_plan ?? [];
  if (days.length === 0) return null;

  return (
    <section data-testid="itinerary-view" style={{ marginTop: 12 }}>
      <ItineraryControls />
      <DayStrip days={days} />
      {days.map((day) => (
        <DaySection key={day.day_index} day={day} items={items} />
      ))}
    </section>
  );
}

function ItineraryControls() {
  return (
    <div
      className="print:hidden"
      data-print-hide
      style={{
        display: "grid",
        gap: 14,
        margin: "0 0 24px",
        padding: "16px 0",
        borderTop: "1px dotted hsl(var(--kraft))",
        borderBottom: "1px dotted hsl(var(--kraft))",
      }}
    >
      <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 18 }}>
        <PerspectiveToggle />
        <LanguageToggle />
      </div>
      <div
        role="tablist"
        aria-label="Report sections"
        style={{ display: "flex", flexWrap: "wrap", gap: "10px 12px" }}
      >
        {TAB_ORDER.map((key, i) => {
          const tilts = ["-2deg", "1.4deg", "-1deg", "2deg", "-1.5deg", "1deg"];
          return (
            <button
              key={key}
              type="button"
              role="tab"
              aria-selected={key === "together"}
              className={`chip ${key === "together" ? "is-on" : ""}`.trim()}
              style={{
                ["--tilt" as never]: tilts[i % tilts.length],
                fontSize: 16,
              }}
              data-tab={key}
            >
              {TAB_LABELS[key]}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function DayStrip({ days }: { days: DayPlanT[] }) {
  return (
    <nav
      aria-label="jump to day"
      style={{
        display: "flex",
        flexWrap: "wrap",
        alignItems: "center",
        gap: "10px 14px",
        margin: "8px 0 28px",
        padding: "12px 14px",
        background: "hsl(var(--paper-2))",
        border: "1px dashed hsl(var(--kraft))",
      }}
    >
      <span className="type" style={{ color: "hsl(var(--ink-3))" }}>
        jump &rarr;
      </span>
      {days.map((day, i) => (
        <a
          key={day.day_index}
          href={`#day-${day.day_index}`}
          className="hand"
          style={{
            fontSize: 20,
            color: "hsl(var(--ink))",
            textDecoration: "none",
            padding: "2px 8px 0",
            ...((i % 2 === 0
              ? { transform: "rotate(-1deg)" }
              : { transform: "rotate(.6deg)" }) as CSSProperties),
          }}
        >
          Day {day.day_index}
          {day.date ? (
            <span
              className="type"
              style={{
                display: "block",
                fontSize: 10,
                color: "hsl(var(--ink-3))",
                marginTop: 2,
              }}
            >
              {day.date}
            </span>
          ) : null}
        </a>
      ))}
    </nav>
  );
}

function DaySection({ day, items }: { day: DayPlanT; items: JoinedItem[] }) {
  // Group slots by period, preserve canonical period order. We don't
  // sort within a period: the backend scheduler emits slots already in
  // intended order, and reordering would risk misrepresenting it.
  const byPeriod = new Map<DaySlotT["period"], DaySlotT[]>();
  for (const slot of day.slots) {
    const arr = byPeriod.get(slot.period) ?? [];
    arr.push(slot);
    byPeriod.set(slot.period, arr);
  }

  return (
    <section
      id={`day-${day.day_index}`}
      style={{ scrollMarginTop: 24, marginTop: 56 }}
      data-testid={`day-section-${day.day_index}`}
    >
      <header
        style={{
          display: "flex",
          alignItems: "flex-end",
          justifyContent: "space-between",
          gap: 18,
          flexWrap: "wrap",
          padding: "10px 0 12px",
          borderBottom: "1px dotted hsl(var(--kraft))",
        }}
      >
        <h2 className="hand-xl" style={{ margin: 0 }}>
          Day {day.day_index}
          {day.theme ? <span style={{ color: "hsl(var(--ink-2))" }}> — {day.theme}</span> : null}
        </h2>
        {day.date ? <p className="annot">{day.date}</p> : null}
      </header>

      {PERIOD_ORDER.filter((p) => (byPeriod.get(p)?.length ?? 0) > 0).map((period) => {
        const slots = byPeriod.get(period) ?? [];
        return (
          <div key={period}>
            <h3
              className="type"
              style={{
                display: "inline-block",
                margin: "24px 0 14px",
                padding: "4px 12px 3px",
                background: "hsl(var(--paper-3))",
                border: "1px solid hsl(var(--kraft))",
              }}
            >
              {PERIOD_LABEL[period]}
            </h3>
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
                gap: 22,
              }}
            >
              {slots.map((slot, idx) => (
                <ItineraryCard
                  key={`${period}-${slot.item_index}-${idx}`}
                  slot={slot}
                  item={items[slot.item_index]}
                  tapeIndex={slot.item_index}
                />
              ))}
            </div>
          </div>
        );
      })}
    </section>
  );
}

function ItineraryCard({
  slot,
  item,
  tapeIndex,
}: {
  slot: DaySlotT;
  item: JoinedItem | undefined;
  tapeIndex: number;
}) {
  if (!item) return null;
  const view = item as JoinedItemView;
  const name = view.candidate?.name ?? "untitled";
  const description = view.long_description || view.summary || "";
  const classification = view.classification;
  const verdict = classification ? (VERDICT_BY_CLASS[classification] ?? null) : null;
  const imageUrl = view.image_url ?? null;
  const tape = TAPE_BY_INDEX[tapeIndex % TAPE_BY_INDEX.length];
  const tilt = (tapeIndex % 3) - 1;

  return (
    <article
      className={imageUrl ? "photo-card" : "photo-card is-typed"}
      style={
        {
          "--tilt": `${tilt}deg`,
          transform: "rotate(var(--tilt, 0deg))",
        } as CSSProperties
      }
    >
      <span className={`tape ${tape} cnr`} />
      {imageUrl ? <img src={imageUrl} alt={name} /> : <div className="photo" data-label={name} />}
      <p className="cap">{name}</p>
      {description ? <p className="scrawl">{description}</p> : null}

      {/* Match-row mirrors the itinerary mockup's compact per-person bar
          (designer's pages/trip-detail-itinerary.html lines 237-240).
          Keeps parity with scrapbook.css's .match-row / .match / .bar
          tokens — we read match_scores defensively because pre-2p items
          lack the field and we just want to omit the row in that case. */}
      <MatchRow item={view} />

      {verdict ? (
        <span className="verdict">
          <span
            aria-hidden="true"
            style={{
              display: "inline-block",
              width: 7,
              height: 7,
              borderRadius: "50%",
              marginRight: 6,
              verticalAlign: 1,
              background: `hsl(var(--signal-${verdict.signal}))`,
            }}
          />
          {verdict.text}
        </span>
      ) : null}

      {slot.note ? (
        <span className="annot" style={{ display: "block", marginTop: 8 }}>
          {slot.note}
        </span>
      ) : null}
    </article>
  );
}

function MatchRow({ item }: { item: JoinedItemView }) {
  const scores = item.match_scores;
  if (!scores) return null;
  const entries = Object.entries(scores).filter(([, v]) => typeof v === "number");
  if (entries.length === 0) return null;
  return (
    <p className="match-row" style={{ marginTop: 10 }}>
      {entries.map(([id, v]) => (
        <span key={id} className="match">
          {id.slice(0, 6)}
          <span className="bar">
            <i style={{ ["--v" as never]: `${Math.round(v * 100)}%` }} />
          </span>
        </span>
      ))}
    </p>
  );
}
