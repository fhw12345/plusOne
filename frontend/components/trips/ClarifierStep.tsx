"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { ApiError } from "@/lib/api/client";
import { clarifyTrip, skipClarify } from "@/lib/api/trips";

/**
 * batch-2t — single-round clarifier rendered inline on the new-trip page.
 * The parent ``TripForm`` swaps its body for this component when
 * ``createTrip()`` returns ``status === "clarifying"``.
 */
export interface ClarifierStepProps {
  tripId: string;
  questions: Array<{ id: string; text: string }>;
}

type FieldErrors = Record<string, string | undefined>;

export function ClarifierStep({ tripId, questions }: ClarifierStepProps) {
  const router = useRouter();
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(questions.map((q) => [q.id, ""])),
  );
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [serverError, setServerError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const heading = "before i go";
  const hint =
    questions.length === 1
      ? "a quick check. one-liners fine."
      : "a couple of quick checks. one-liners fine.";

  const navigateToTrip = () => {
    router.push(`/app/trips/${tripId}`);
  };

  const onSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (submitting) return;
    // Per-field validation: every textarea must have non-empty trimmed text.
    const errs: FieldErrors = {};
    for (const q of questions) {
      const v = (values[q.id] ?? "").trim();
      if (!v) errs[q.id] = "give me something here or skip.";
    }
    if (Object.keys(errs).length > 0) {
      setFieldErrors(errs);
      return;
    }
    setFieldErrors({});
    setServerError(null);
    setSubmitting(true);
    try {
      await clarifyTrip(
        tripId,
        questions.map((q) => ({ id: q.id, text: (values[q.id] ?? "").trim() })),
      );
      navigateToTrip();
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        // Trip already left ``clarifying`` (double-submit / second tab).
        // Per PRD §3 scenario D: navigate anyway.
        setServerError("already started — opening it for you…");
        navigateToTrip();
        return;
      }
      if (err instanceof ApiError && err.status === 422) {
        setServerError("didn't quite catch that — try again?");
        setSubmitting(false);
        return;
      }
      setServerError("something snagged on the wire. one more try?");
      setSubmitting(false);
    }
  };

  const onSkip = async () => {
    if (submitting) return;
    setFieldErrors({});
    setServerError(null);
    setSubmitting(true);
    try {
      await skipClarify(tripId);
      navigateToTrip();
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        navigateToTrip();
        return;
      }
      setServerError("something snagged on the wire. one more try?");
      setSubmitting(false);
    }
  };

  return (
    <form
      onSubmit={onSubmit}
      noValidate
      data-testid="clarifier-step"
      style={{
        position: "relative",
        padding: "36px 38px 42px",
        background: "hsl(var(--paper-2))",
        boxShadow: "0 14px 28px -14px hsl(0 0% 0% / .22)",
        border: "1px solid hsl(var(--kraft))",
      }}
    >
      <span
        className="tape tape--mint"
        style={{ top: -12, left: 36, width: 110, height: 24, transform: "rotate(-3deg)" }}
      />
      <span
        className="tape tape--blue"
        style={{ top: -12, right: 80, width: 80, height: 24, transform: "rotate(2deg)" }}
      />

      <h2 className="scrawl" style={{ fontSize: 22, marginBottom: 6 }}>
        {heading}
      </h2>
      <p className="hint" style={{ marginBottom: 20 }}>
        {hint}
      </p>

      {questions.map((q) => (
        <div className="field" key={q.id}>
          <label htmlFor={`clar-${q.id}`} className="annot" style={{ display: "block" }}>
            {q.text}
          </label>
          <textarea
            id={`clar-${q.id}`}
            data-testid={`clarifier-input-${q.id}`}
            rows={2}
            value={values[q.id] ?? ""}
            onChange={(e) =>
              setValues((prev) => ({ ...prev, [q.id]: e.target.value }))
            }
            aria-invalid={fieldErrors[q.id] ? "true" : "false"}
            disabled={submitting}
            style={{ width: "100%" }}
          />
          {fieldErrors[q.id] ? (
            <span
              role="alert"
              className="annot"
              style={{ display: "block", marginTop: 6 }}
            >
              {fieldErrors[q.id]}
            </span>
          ) : null}
        </div>
      ))}

      <div style={{ display: "flex", alignItems: "center", gap: 22, marginTop: 28 }}>
        <button
          type="submit"
          disabled={submitting}
          className="btn btn--red"
          style={{ opacity: submitting ? 0.55 : 1 }}
        >
          {submitting ? "off i go…" : "go look →"}
        </button>
        <button
          type="button"
          onClick={onSkip}
          disabled={submitting}
          className="scrawl"
          style={{
            background: "none",
            border: "none",
            padding: 0,
            color: "inherit",
            cursor: "pointer",
            textDecoration: "underline",
            fontSize: 14,
          }}
        >
          skip these →
        </button>
      </div>

      {serverError ? (
        <p role="alert" className="annot" style={{ marginTop: 18, display: "block" }}>
          {serverError}
        </p>
      ) : null}
    </form>
  );
}
