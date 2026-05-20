"use client";

import { useMemo } from "react";

import { ItemCard } from "@/components/trips/ItemCard";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { JoinedItem } from "@/lib/schemas/trips";
import { categorize, TAB_EMPTY_COPY, TAB_LABELS, TAB_ORDER } from "@/lib/trips/categorize";

export interface ReportTabsProps {
  items: JoinedItem[];
}

export function ReportTabs({ items }: ReportTabsProps) {
  const buckets = useMemo(() => categorize(items), [items]);

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
              <p className="text-foreground/70 text-sm">{TAB_EMPTY_COPY[key]}</p>
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
