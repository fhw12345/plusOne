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
      // Strip empty free_text so backend sees `null`/absent instead of "".
      // Same for companion_ids: drop the field when empty so the wire body
      // stays a tight `{destination}` for the common "no companions yet" case.
      const body: CreateTripBodyT = {
        destination: values.destination,
        ...(values.free_text && values.free_text.length > 0 ? { free_text: values.free_text } : {}),
        ...(values.companion_ids && values.companion_ids.length > 0
          ? { companion_ids: values.companion_ids }
          : {}),
      };
      const res = await createTrip(body);
      router.push(`/app/trips/${res.trip_id}`);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setServerError("Session expired. Sign in again.");
      } else if (err instanceof ApiError) {
        setServerError(err.message || "Something went wrong. Please try again.");
      } else {
        setServerError("Something went wrong. Please try again.");
      }
    }
  };

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-4" noValidate>
      <label className="flex flex-col gap-2 text-sm">
        <span>Where to?</span>
        <input
          type="text"
          autoComplete="off"
          aria-label="Destination"
          className="border-foreground/20 rounded border px-3 py-2 text-base"
          {...register("destination")}
          aria-invalid={errors.destination ? "true" : "false"}
        />
        {errors.destination ? (
          <span role="alert" className="text-sm text-red-600">
            {errors.destination.message}
          </span>
        ) : null}
      </label>

      <label className="flex flex-col gap-2 text-sm">
        <span>Notes</span>
        <textarea
          rows={4}
          className="border-foreground/20 rounded border px-3 py-2 text-base"
          {...register("free_text")}
          aria-invalid={errors.free_text ? "true" : "false"}
        />
        {errors.free_text ? (
          <span role="alert" className="text-sm text-red-600">
            {errors.free_text.message}
          </span>
        ) : null}
      </label>

      <Controller
        control={control}
        name="companion_ids"
        render={({ field }) => (
          <CompanionSelector value={field.value ?? []} onChange={field.onChange} />
        )}
      />

      <button
        type="submit"
        disabled={isSubmitting}
        className="bg-foreground text-background rounded px-4 py-2 text-sm font-medium disabled:opacity-50"
      >
        {isSubmitting ? "Planning…" : "Plan trip"}
      </button>

      {serverError ? (
        <p role="alert" className="text-sm text-red-600">
          {serverError}
        </p>
      ) : null}
    </form>
  );
}
