"use client";

import { useMemo, useState } from "react";

import { ItemCard } from "@/components/trips/ItemCard";
import { useReportPrefsHasHydrated } from "@/hooks/useReportPrefsHasHydrated";
import type { JoinedItem, JoinedItemView } from "@/lib/schemas/trips";
import { categorize, TAB_EMPTY_COPY, TAB_LABELS, TAB_ORDER, type TabKey } from "@/lib/trips/categorize";
import { useReportPrefsStore, type Perspective } from "@/store/reportPrefs";

export interface ReportTabsProps {
  items: JoinedItem[];
}

function filterByPerspective(items: JoinedItem[], perspective: Perspective): JoinedItem[] {
  if (perspective === "fused") return items;
  return items.filter((item) => {
    const view = item as JoinedItemView;
    const side = perspective === "en" ? view.classification_en : view.classification_zh;
    return side != null;
  });
}

export function ReportTabs({ items }: ReportTabsProps) {
  const hydrated = useReportPrefsHasHydrated();
  const persistedPerspective = useReportPrefsStore((s) => s.perspective);
  const perspective: Perspective = hydrated ? persistedPerspective : "fused";

  const [active, setActive] = useState<TabKey>("together");

  const buckets = useMemo(() => {
    const filtered = filterByPerspective(items, perspective);
    const out = categorize(filtered);
    out.disagreement = categorize(items).disagreement;
    return out;
  }, [items, perspective]);

  const allHiddenForPerspective =
    perspective !== "fused" && items.length > 0 && buckets.together.length === 0;

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
                {key !== "disagreement" && allHiddenForPerspective
                  ? "this reading was written before per-voice tags. switch back to blended to see the picks."
                  : TAB_EMPTY_COPY[key]}
              </p>
            ) : (
              <ul style={{ listStyle: "none", padding: 0, display: "grid", gap: 16 }}>
                {bucket.map((item, idx) => (
                  <li key={idx}>
                    <ItemCard item={item} index={idx} />
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
