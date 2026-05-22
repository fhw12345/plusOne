"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Controller, useForm } from "react-hook-form";

import { ClarifierStep } from "@/components/trips/ClarifierStep";
import { CompanionSelector } from "@/components/trips/CompanionSelector";
import { DestinationCombobox } from "@/components/trips/DestinationCombobox";
import { createTrip } from "@/lib/api/trips";
import { ApiError } from "@/lib/api/client";
import {
  CURRENCIES,
  CreateTripBody,
  type CreateTripBody as CreateTripBodyT,
} from "@/lib/schemas/trips";

// Batch-2o: native ``<input type="date">`` exposes ``YYYY-MM-DD`` strings.
// The wire format (mirrored by zod ``CreateTripBody``) is ISO with
// offset; we pin to UTC midnight at the form boundary so a user in any
// timezone gets a stable, comparable date back from ``TripDetail`` later.
function dateInputToIso(value: string | undefined | null): string | undefined {
  if (!value) return undefined;
  return new Date(`${value}T00:00:00Z`).toISOString();
}

export function TripForm() {
  const router = useRouter();
  const [serverError, setServerError] = useState<string | null>(null);
  // batch-2t: when the backend returns ``status="clarifying"`` with 1–3
  // questions, we swap the form body for ``<ClarifierStep>`` instead of
  // navigating. Null = render the form; non-null = render the clarifier.
  const [clarifierState, setClarifierState] = useState<
    { tripId: string; questions: Array<{ id: string; text: string }> } | null
  >(null);

  const {
    control,
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<CreateTripBodyT>({
    resolver: zodResolver(CreateTripBody),
    mode: "onSubmit",
    defaultValues: {
      destination: "",
      free_text: "",
      companion_ids: [],
      // Batch-2o defaults: dates empty (skipped unless user picks);
      // currency defaults to USD as a sensible starting point per PRD.
      date_start: undefined,
      date_end: undefined,
      budget_amount: undefined,
      budget_currency: "USD",
    },
  });

  const onSubmit = async (values: CreateTripBodyT) => {
    setServerError(null);
    try {
      // ``date_start`` / ``date_end`` are already ISO strings here —
      // ``setValueAs`` on the date inputs converts YYYY-MM-DD to UTC ISO
      // at registration time so zod's ``datetime({offset:true})`` accepts
      // them and the cross-field check sees comparable strings.
      const body: CreateTripBodyT = {
        destination: values.destination,
        ...(values.free_text && values.free_text.length > 0
          ? { free_text: values.free_text }
          : {}),
        ...(values.companion_ids && values.companion_ids.length > 0
          ? { companion_ids: values.companion_ids }
          : {}),
        ...(values.date_start ? { date_start: values.date_start } : {}),
        ...(values.date_end ? { date_end: values.date_end } : {}),
        ...(typeof values.budget_amount === "number"
          ? { budget_amount: values.budget_amount }
          : {}),
        ...(values.budget_currency ? { budget_currency: values.budget_currency } : {}),
      };
      const res = await createTrip(body);
      // batch-2t: if the clarifier emitted questions, park here and let
      // the user answer them inline. Otherwise navigate as before.
      if (
        res.status === "clarifying" &&
        res.clarifier_questions &&
        res.clarifier_questions.length > 0
      ) {
        setClarifierState({
          tripId: res.trip_id,
          questions: res.clarifier_questions,
        });
        return;
      }
      router.push(`/app/trips/${res.trip_id}`);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setServerError("your link timed out. sign in again?");
      } else if (err instanceof ApiError) {
        setServerError(err.message || "something snagged on the wire. one more try?");
      } else {
        setServerError("something snagged. try again.");
      }
    }
  };

  if (clarifierState !== null) {
    return (
      <ClarifierStep
        tripId={clarifierState.tripId}
        questions={clarifierState.questions}
      />
    );
  }

  return (
    <form
      onSubmit={handleSubmit(onSubmit)}
      noValidate
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

      <div className="field">
        <label htmlFor="dest">the place</label>
        <Controller
          control={control}
          name="destination"
          render={({ field }) => (
            <DestinationCombobox
              value={field.value ?? ""}
              onChange={field.onChange}
              onBlur={field.onBlur}
              error={errors.destination?.message}
              inputId="dest"
            />
          )}
        />
        <span className="hint">i&rsquo;ll suggest as you type.</span>
        {errors.destination ? (
          <span role="alert" className="annot" style={{ display: "block", marginTop: 6 }}>
            {errors.destination.message}
          </span>
        ) : null}
      </div>

      {/* Batch-2o: dates side-by-side, then budget+currency on its own row.
          All four inputs are optional — the form is happy to ship a trip
          with destination only. */}
      <div className="field">
        <label>when</label>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            gap: 14,
          }}
        >
          <div>
            <label htmlFor="date_start" className="hint" style={{ display: "block" }}>
              from
            </label>
            <input
              id="date_start"
              type="date"
              {...register("date_start", {
                setValueAs: (v) => dateInputToIso(v as string | undefined),
              })}
              aria-invalid={errors.date_start ? "true" : "false"}
              style={{ width: "100%" }}
            />
          </div>
          <div>
            <label htmlFor="date_end" className="hint" style={{ display: "block" }}>
              to
            </label>
            <input
              id="date_end"
              type="date"
              {...register("date_end", {
                setValueAs: (v) => dateInputToIso(v as string | undefined),
              })}
              aria-invalid={errors.date_end ? "true" : "false"}
              style={{ width: "100%" }}
            />
          </div>
        </div>
        <span className="hint">optional. skip if you haven&rsquo;t picked yet.</span>
        {errors.date_end ? (
          <span role="alert" className="annot" style={{ display: "block", marginTop: 6 }}>
            {errors.date_end.message}
          </span>
        ) : null}
      </div>

      <div className="field">
        <label>your budget</label>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "2fr 1fr",
            gap: 14,
          }}
        >
          <div>
            <label htmlFor="budget_amount" className="hint" style={{ display: "block" }}>
              how much, roughly
            </label>
            <input
              id="budget_amount"
              type="number"
              inputMode="numeric"
              min={0}
              step={1}
              placeholder="2500"
              {...register("budget_amount", {
                setValueAs: (v) =>
                  v === "" || v === null || v === undefined ? undefined : Number(v),
              })}
              aria-invalid={errors.budget_amount ? "true" : "false"}
              style={{ width: "100%" }}
            />
          </div>
          <div>
            <label htmlFor="budget_currency" className="hint" style={{ display: "block" }}>
              currency
            </label>
            <select
              id="budget_currency"
              {...register("budget_currency")}
              aria-invalid={errors.budget_currency ? "true" : "false"}
              style={{ width: "100%" }}
            >
              {CURRENCIES.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </div>
        </div>
        <span className="hint">
          optional. round numbers are fine &mdash; it&rsquo;s a hint, not a ceiling.
        </span>
        {errors.budget_amount ? (
          <span role="alert" className="annot" style={{ display: "block", marginTop: 6 }}>
            {errors.budget_amount.message}
          </span>
        ) : null}
        {errors.budget_currency ? (
          <span role="alert" className="annot" style={{ display: "block", marginTop: 6 }}>
            {errors.budget_currency.message}
          </span>
        ) : null}
      </div>

      <div className="field">
        <label>who you&rsquo;re bringing</label>
        <Controller
          control={control}
          name="companion_ids"
          render={({ field }) => (
            <CompanionSelector value={field.value ?? []} onChange={field.onChange} />
          )}
        />
        <span className="hint" style={{ marginTop: 14 }}>
          tap the names you&rsquo;re bringing. i&rsquo;ll plan around them.
        </span>
      </div>

      <div className="field">
        <label htmlFor="mood">the mood, the foods, what to avoid</label>
        <textarea
          id="mood"
          rows={5}
          placeholder="tonkotsu ramen. quiet counters. nothing instagrammy."
          {...register("free_text")}
          aria-invalid={errors.free_text ? "true" : "false"}
        />
        <span className="hint">
          say it like you&rsquo;d tell a friend. dealbreakers go up top.
        </span>
        {errors.free_text ? (
          <span role="alert" className="annot" style={{ display: "block", marginTop: 6 }}>
            {errors.free_text.message}
          </span>
        ) : null}
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 22, marginTop: 28 }}>
        <button
          type="submit"
          disabled={isSubmitting}
          className="btn btn--red"
          style={{ opacity: isSubmitting ? 0.55 : 1 }}
        >
          {isSubmitting ? "off i go…" : "go look →"}
        </button>
        <span className="scrawl" style={{ fontSize: 14 }}>
          i&rsquo;ll start scribbling the moment you press it.
          <br />
          takes about 90 seconds.
        </span>
      </div>

      {serverError ? (
        <p role="alert" className="annot" style={{ marginTop: 18, display: "block" }}>
          {serverError}
        </p>
      ) : null}
    </form>
  );
}
