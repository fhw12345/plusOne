"use client";

import { cn } from "@/lib/utils";
import { useReportPrefsStore, type Perspective } from "@/store/reportPrefs";
import { useReportPrefsHasHydrated } from "@/hooks/useReportPrefsHasHydrated";

interface Option {
  value: Perspective;
  label: string;
}

const OPTIONS: Option[] = [
  { value: "zh", label: "中文社区" },
  { value: "en", label: "English community" },
  { value: "fused", label: "Fused" },
];

/**
 * Segmented control for the report perspective filter. Pure view-side —
 * never re-runs the cycle. Uses ``role="radiogroup"`` semantics so screen
 * readers announce it as a single grouped choice.
 *
 * Renders a no-op placeholder until the persisted store rehydrates, so
 * the first client paint matches SSR.
 */
export function PerspectiveToggle() {
  const hydrated = useReportPrefsHasHydrated();
  const perspective = useReportPrefsStore((s) => s.perspective);
  const setPerspective = useReportPrefsStore((s) => s.setPerspective);

  return (
    <div
      role="radiogroup"
      aria-label="Report perspective"
      data-testid="perspective-toggle"
      className="bg-muted inline-flex items-center gap-1 rounded-md p-1"
    >
      {OPTIONS.map((opt) => {
        const active = hydrated && perspective === opt.value;
        return (
          <button
            key={opt.value}
            type="button"
            role="radio"
            aria-checked={active}
            data-perspective={opt.value}
            onClick={() => setPerspective(opt.value)}
            className={cn(
              "focus-visible:ring-foreground/60 rounded px-3 py-1 text-xs font-medium transition-colors focus-visible:ring-2 focus-visible:outline-none",
              active
                ? "bg-background text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}
