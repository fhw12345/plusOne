"use client";

import { useState } from "react";

import { useRefineTrip } from "@/hooks/useRefineTrip";
import { ApiError } from "@/lib/api/client";

export interface RefinePanelProps {
  tripId: string;
  /** True while a cycle is mid-flight — disables the submit button. */
  disabled?: boolean;
  /** Optional callback fired after a successful refine submission with
   * the pre-allocated id of the in-flight new report. */
  onSubmitted?: (newReportId: string) => void;
}

const HEADER = "tweak it";
const HINT = "tell me what to change. one line.";
const PLACEHOLDER = "swap kyoto temple → arashiyama instead";
const SUBMIT_IDLE = "off i go again";
const SUBMIT_PENDING = "scribbling…";

const ERROR_409_BUSY = "still working on the last one. give it a moment.";
const ERROR_403 = "this one's read-only — you can't tweak someone else's reading.";
const ERROR_GENERIC = "something snagged. one more try?";

/**
 * Sticky-note style refine input. Renders below the report on a
 * completed trip. Submits the hint to the backend and lets the existing
 * SSE stream (keyed by trip_id) pick up the new cycle.
 *
 * On 409 / 403 we surface the inline scrawl. The backend usually 404s
 * cross-user trips for opacity (matching ``delete_trip``), but we keep
 * the 403 copy in case the policy ever loosens.
 */
export function RefinePanel({ tripId, disabled = false, onSubmitted }: RefinePanelProps) {
  const [hint, setHint] = useState("");
  const [errorCopy, setErrorCopy] = useState<string | null>(null);
  const mutation = useRefineTrip(tripId);

  const trimmed = hint.trim();
  const canSubmit = !disabled && !mutation.isPending && trimmed.length > 0;

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!canSubmit) return;
    setErrorCopy(null);
    try {
      const result = await mutation.mutateAsync({ hint: trimmed });
      setHint("");
      onSubmitted?.(result.report_id);
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 409) {
          setErrorCopy(ERROR_409_BUSY);
        } else if (err.status === 403) {
          setErrorCopy(ERROR_403);
        } else {
          setErrorCopy(ERROR_GENERIC);
        }
      } else {
        setErrorCopy(ERROR_GENERIC);
      }
    }
  };

  return (
    <section
      data-testid="refine-panel"
      style={{
        position: "relative",
        marginTop: 28,
        padding: "26px 28px 28px",
        background: "hsl(var(--paper-2))",
        border: "1px solid hsl(var(--kraft))",
        boxShadow: "0 12px 24px -16px hsl(0 0% 0% / .22)",
      }}
    >
      <span
        className="tape tape--blue"
        style={{ top: -10, right: 40, width: 90, height: 22, transform: "rotate(2deg)" }}
      />
      <header style={{ marginBottom: 14 }}>
        <h2 className="hand-lg" style={{ fontSize: 28 }}>
          {HEADER}
        </h2>
        <p className="scrawl" style={{ fontSize: 14, marginTop: 4 }}>
          {HINT}
        </p>
      </header>

      <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <textarea
          data-testid="refine-hint"
          rows={2}
          value={hint}
          onChange={(e) => setHint(e.target.value)}
          placeholder={PLACEHOLDER}
          maxLength={500}
          disabled={disabled || mutation.isPending}
          style={{ width: "100%", padding: "10px 12px", font: "inherit", fontSize: 16 }}
        />

        {errorCopy ? (
          <p role="alert" data-testid="refine-error" className="annot" style={{ display: "block" }}>
            {errorCopy}
          </p>
        ) : null}

        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <button
            type="submit"
            data-testid="refine-submit"
            disabled={!canSubmit}
            className="btn btn--red"
            style={{ opacity: canSubmit ? 1 : 0.55 }}
          >
            {mutation.isPending ? SUBMIT_PENDING : SUBMIT_IDLE}
          </button>
        </div>
      </form>
    </section>
  );
}
