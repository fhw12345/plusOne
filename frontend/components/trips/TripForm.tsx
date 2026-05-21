"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Controller, useForm } from "react-hook-form";

import { CompanionSelector } from "@/components/trips/CompanionSelector";
import { createTrip } from "@/lib/api/trips";
import { ApiError } from "@/lib/api/client";
import { CreateTripBody, type CreateTripBody as CreateTripBodyT } from "@/lib/schemas/trips";

export function TripForm() {
  const router = useRouter();
  const [serverError, setServerError] = useState<string | null>(null);

  const {
    control,
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<CreateTripBodyT>({
    resolver: zodResolver(CreateTripBody),
    mode: "onSubmit",
    defaultValues: { destination: "", free_text: "", companion_ids: [] },
  });

  const onSubmit = async (values: CreateTripBodyT) => {
    setServerError(null);
    try {
      const body: CreateTripBodyT = {
        destination: values.destination,
        ...(values.free_text && values.free_text.length > 0
          ? { free_text: values.free_text }
          : {}),
        ...(values.companion_ids && values.companion_ids.length > 0
          ? { companion_ids: values.companion_ids }
          : {}),
      };
      const res = await createTrip(body);
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
        <input
          id="dest"
          type="text"
          autoComplete="off"
          placeholder="e.g. tokyo · kyoto · taipei"
          {...register("destination")}
          aria-invalid={errors.destination ? "true" : "false"}
        />
        <span className="hint">
          a city is best. neighborhoods are okay too &mdash; i can zoom in.
        </span>
        {errors.destination ? (
          <span role="alert" className="annot" style={{ display: "block", marginTop: 6 }}>
            {errors.destination.message}
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
