"use client";

import { cn } from "@/lib/utils";
import { useReportPrefsStore, type ReportLanguage } from "@/store/reportPrefs";
import { useReportPrefsHasHydrated } from "@/hooks/useReportPrefsHasHydrated";

interface Option {
  value: ReportLanguage;
  label: string;
}

// Order matches the PRD's "[中文] [English]" segmented control. The
// "Original" position is implicit — when neither zh nor en translations
// exist (old reports / translator disabled), the report falls back to
// the source-language items.
const OPTIONS: Option[] = [
  { value: "zh", label: "中文" },
  { value: "en", label: "English" },
];

/**
 * Segmented control for the output-language toggle. Pure view-side —
 * never re-runs the cycle. Uses ``role="radiogroup"`` semantics so screen
 * readers announce it as a single grouped choice.
 *
 * Renders no option as active until ``useReportPrefsHasHydrated`` flips
 * post-rehydrate, so first client paint matches SSR.
 */
export function LanguageToggle() {
  const hydrated = useReportPrefsHasHydrated();
  const language = useReportPrefsStore((s) => s.language);
  const setLanguage = useReportPrefsStore((s) => s.setLanguage);

  return (
    <div
      role="radiogroup"
      aria-label="Report language"
      data-testid="language-toggle"
      className="bg-muted inline-flex items-center gap-1 rounded-md p-1"
    >
      {OPTIONS.map((opt) => {
        const active = hydrated && language === opt.value;
        return (
          <button
            key={opt.value}
            type="button"
            role="radio"
            aria-checked={active}
            data-language={opt.value}
            onClick={() => setLanguage(opt.value)}
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
