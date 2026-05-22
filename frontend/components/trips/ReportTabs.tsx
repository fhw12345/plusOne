"use client";

import { useMemo, useState } from "react";

import { ItemCard } from "@/components/trips/ItemCard";
import { useReportPrefsHasHydrated } from "@/hooks/useReportPrefsHasHydrated";
import type { JoinedItem } from "@/lib/schemas/trips";
import { categorize, TAB_EMPTY_COPY, TAB_LABELS, TAB_ORDER, type Party, type TabKey } from "@/lib/trips/categorize";
import { useReportPrefsStore, type Perspective } from "@/store/reportPrefs";

export interface ReportTabsProps {
  items: JoinedItem[];
  // Batch-2p: the trip's party (user + companions) used to route items
  // into ``user_only`` / ``partner_only`` and to label per-card scores.
  // Optional — old reports / shared endpoint pre-2p pass nothing.
  party?: Party | null;
  partyNames?: Record<string, string>;
}

export function ReportTabs({ items, party = null, partyNames }: ReportTabsProps) {
  const hydrated = useReportPrefsHasHydrated();
  const persistedPerspective = useReportPrefsStore((s) => s.perspective);
  const perspective: Perspective = hydrated ? persistedPerspective : "fused";

  const [active, setActive] = useState<TabKey>("together");

  // Per PRD batch-2r §4.2(c): no more pre-filter by perspective. Items
  // are never hidden — they just re-classify via `resolveClassification`
  // inside `categorize`. `disagreement` is perspective-independent by
  // construction (computed from the raw zh/en pair). Batch-2p threads
  // ``party`` into the score-gated tabs.
  const buckets = useMemo(
    () => categorize(items, perspective, party),
    [items, perspective, party],
  );

  return (
    <div role="tablist" aria-label="Report sections" style={{ display: "flex", flexDirection: "column", gap: 18 }}>
      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: "10px 12px",
          paddingBottom: 12,
          borderBottom: "1px dotted hsl(var(--kraft))",
        }}
      >
        {TAB_ORDER.map((key, i) => {
          const isActive = key === active;
          const count = buckets[key].length;
          const tilts = ["-2deg", "1.4deg", "-1deg", "2deg", "-1.5deg", "1deg"];
          return (
            <button
              key={key}
              type="button"
              role="tab"
              aria-selected={isActive}
              aria-controls={`panel-${key}`}
              onClick={() => setActive(key)}
              className={`chip ${isActive ? "is-on" : ""}`.trim()}
              style={{
                ["--tilt" as never]: tilts[i % tilts.length],
                fontSize: 16,
              }}
              data-tab={key}
            >
              {TAB_LABELS[key]}
              {count > 0 ? (
                <span
                  className="meta"
                  style={{
                    marginLeft: 6,
                    fontSize: 12,
                    color: "hsl(var(--ink-3))",
                  }}
                >
                  {count}
                </span>
              ) : null}
            </button>
          );
        })}
      </div>

      {TAB_ORDER.map((key) => {
        if (key !== active) return null;
        const bucket = buckets[key];
        return (
          <div
            key={key}
            role="tabpanel"
            id={`panel-${key}`}
            aria-label={TAB_LABELS[key]}
          >
            {bucket.length === 0 ? (
              <p
                className="scrawl"
                style={{ fontSize: 15, color: "hsl(var(--ink-3))" }}
                data-testid={`tab-empty-${key}`}
              >
                {TAB_EMPTY_COPY[key]}
              </p>
            ) : (
              <ul style={{ listStyle: "none", padding: 0, display: "grid", gap: 16 }}>
                {bucket.map((item, idx) => (
                  <li key={idx}>
                    <ItemCard
                      item={item}
                      index={idx}
                      perspective={perspective}
                      party={party}
                      partyNames={partyNames}
                    />
                  </li>
                ))}
              </ul>
            )}
          </div>
        );
      })}
    </div>
  );
}
