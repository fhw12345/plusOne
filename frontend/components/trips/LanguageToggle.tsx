"use client";

import { useReportPrefsStore, type ReportLanguage } from "@/store/reportPrefs";
import { useReportPrefsHasHydrated } from "@/hooks/useReportPrefsHasHydrated";

interface Option {
  value: ReportLanguage;
  label: string;
}

const OPTIONS: Option[] = [
  { value: "zh", label: "中文" },
  { value: "en", label: "English" },
];

export function LanguageToggle() {
  const hydrated = useReportPrefsHasHydrated();
  const language = useReportPrefsStore((s) => s.language);
  const setLanguage = useReportPrefsStore((s) => s.setLanguage);

  return (
    <div
      role="radiogroup"
      aria-label="Report language"
      data-testid="language-toggle"
      style={{ display: "inline-flex", alignItems: "center", gap: 8 }}
    >
      <span className="type" style={{ marginRight: 4 }}>
        read in
      </span>
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
            className={`chip ${active ? "is-on" : ""}`.trim()}
            style={{
              ["--tilt" as never]: active ? "1.4deg" : "0deg",
              fontSize: 15,
            }}
          >
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}
