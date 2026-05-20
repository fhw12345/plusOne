"use client";

import { useMemo } from "react";

import { ItemCard } from "@/components/trips/ItemCard";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useReportPrefsHasHydrated } from "@/hooks/useReportPrefsHasHydrated";
import type { JoinedItem, JoinedItemView } from "@/lib/schemas/trips";
import { categorize, TAB_EMPTY_COPY, TAB_LABELS, TAB_ORDER } from "@/lib/trips/categorize";
import { useReportPrefsStore, type Perspective } from "@/store/reportPrefs";

export interface ReportTabsProps {
  items: JoinedItem[];
}

// Filter items by the active perspective. ``fused`` is identity; the
// per-language perspectives drop items lacking the corresponding side.
// Used for every tab EXCEPT ``disagreement`` (which is perspective-
// independent per PRD batch2i §2).
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
  // Until rehydrate completes, render the SSR-default ``fused`` view so
  // first client paint matches the server.
  const perspective: Perspective = hydrated ? persistedPerspective : "fused";

  const buckets = useMemo(() => {
    const filtered = filterByPerspective(items, perspective);
    const out = categorize(filtered);
    // Disagreement is perspective-independent — recompute from the
    // unfiltered list so switching perspective never hides a divergent
    // item from the disagreement tab.
    out.disagreement = categorize(items).disagreement;
    return out;
  }, [items, perspective]);

  const allHiddenForPerspective =
    perspective !== "fused" && items.length > 0 && buckets.together.length === 0;

  return (
    <Tabs defaultValue="together" className="flex flex-col gap-3">
      <TabsList>
        {TAB_ORDER.map((key) => (
          <TabsTrigger key={key} value={key}>
            {TAB_LABELS[key]}
          </TabsTrigger>
        ))}
      </TabsList>
      {TAB_ORDER.map((key) => {
        const bucket = buckets[key];
        return (
          <TabsContent key={key} value={key}>
            {bucket.length === 0 ? (
              <p className="text-foreground/70 text-sm" data-testid={`tab-empty-${key}`}>
                {key !== "disagreement" && allHiddenForPerspective
                  ? "This report was produced before per-language classification; switch to Fused to see results."
                  : TAB_EMPTY_COPY[key]}
              </p>
            ) : (
              <ul className="flex flex-col gap-3">
                {bucket.map((item, idx) => (
                  <li key={idx}>
                    <ItemCard item={item} />
                  </li>
                ))}
              </ul>
            )}
          </TabsContent>
        );
      })}
    </Tabs>
  );
}
