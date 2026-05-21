"use client";

import { useReportPrefsStore, type Perspective } from "@/store/reportPrefs";
import { useReportPrefsHasHydrated } from "@/hooks/useReportPrefsHasHydrated";

interface Option {
  value: Perspective;
  label: string;
}

const OPTIONS: Option[] = [
  { value: "zh", label: "中文社区" },
  { value: "en", label: "English community" },
  { value: "fused", label: "blended" },
];

export function PerspectiveToggle() {
  const hydrated = useReportPrefsHasHydrated();
  const perspective = useReportPrefsStore((s) => s.perspective);
  const setPerspective = useReportPrefsStore((s) => s.setPerspective);

  return (
    <div
      role="radiogroup"
      aria-label="Report perspective"
      data-testid="perspective-toggle"
      style={{ display: "inline-flex", alignItems: "center", gap: 8 }}
    >
      <span className="type" style={{ marginRight: 4 }}>
        whose voice
      </span>
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
            className={`chip ${active ? "is-on" : ""}`.trim()}
            style={{
              ["--tilt" as never]: active ? "-1.5deg" : "0deg",
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
